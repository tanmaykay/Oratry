from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from urllib.parse import urlencode
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core import DomainError
from app.models import AnalysisResult, AnalysisRun, Assignment, Attempt, Challenge, DictionaryEntry, EmailVerificationChallenge, SkillEvidence as SkillEvidenceRecord, SkillState, User, VocabularyItem
from app.email import EmailDeliveryError, EmailProvider
from app.dictionary import DictionaryProvider, DictionaryProviderError
from app.personalization.skill_engine import SkillEvidence, SkillStateProjection, update_skill_state
from app.personalization.baseline_policy import baseline_assignments, baseline_progress, recommend_after_baseline
from app.personalization.challenge_engine import ChallengeCandidate
from app.providers import DemoTranscriber, RulesEvaluator
WEIGHTS={"structure":.25,"clarity":.20,"fluency":.20,"language":.20,"delivery":.15}
def score(dimensions):
    values={key:max(0,min(100,int(dimensions[key]))) for key in WEIGHTS}
    return {**values,"overall":round(sum(values[k]*w for k,w in WEIGHTS.items())),"scale":"0-100","scorerVersion":"1","weights":WEIGHTS}
def metrics_for(transcript,duration):
    words=transcript.text.split(); fillers=sum(w.strip(".,!").lower() in {"um","uh","like"} for w in words)
    return {"durationSeconds":duration,"wordCount":len(words),"wordsPerMinute":round(len(words)/duration*60,1),"fillerCount":fillers,"fillerRate":round(fillers/max(len(words),1),3),"calculationVersion":"1"}
def recommendation(scores):
    weakest=min(WEIGHTS,key=lambda k:scores[k]); return {"focusSkill":weakest,"observation":f"{weakest.title()} is the greatest current score gap.","action":f"On your retry, prepare one specific improvement for {weakest}.","successCriterion":f"Improve your {weakest} score on the next attempt."}
class AnalysisService:
    def __init__(self,db,stt=None,evaluator=None): self.db,self.stt,self.evaluator=db,stt or DemoTranscriber(),evaluator or RulesEvaluator()
    def process(self,attempt_id):
        attempt=self.db.get(Attempt,attempt_id); run=self.db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id==attempt_id).order_by(AnalysisRun.version.desc()))
        if not attempt or not run or attempt.status=="completed": return
        try:
            attempt.status=run.status="analyzing"; run.current_stage="transcription"; self.db.commit()
            transcript=self.stt.transcribe(attempt.object_key or ""); self._put(run,"transcript",{"text":transcript.text,"segments":transcript.segments,"language":transcript.language,"confidence":transcript.confidence,"provider":transcript.provider,"model":transcript.model})
            run.current_stage="metrics"; objective=metrics_for(transcript,attempt.duration_seconds or 1); self._put(run,"metrics",objective)
            run.current_stage="evaluation"; assignment=self.db.get(Assignment,attempt.assignment_id); challenge=self.db.get(Challenge,assignment.challenge_id); evaluation=self.evaluator.evaluate(transcript,challenge.prompt,objective); self._put(run,"evaluation",{"dimensionObservations":evaluation.observations,"evidence":evaluation.evidence,"provider":evaluation.provider,"model":evaluation.model,"rubricVersion":challenge.rubric_version})
            run.current_stage="scoring"; scorecard=score(evaluation.dimensions); self._put(run,"scorecard",scorecard); run.current_stage="feedback"; self._put(run,"feedback",recommendation(scorecard))
            # Preserve each result as evidence, then replace only the derived projection.
            # Re-running this completed attempt exits above, so evidence is idempotent.
            # Rubric "clarity" contributes evidence to the V1 Thinking profile;
            # skill states retain the fixed taxonomy in the domain model.
            skill_scores={"thinking": scorecard["clarity"], "structure": scorecard["structure"],
                          "language": scorecard["language"], "fluency": scorecard["fluency"], "delivery": scorecard["delivery"]}
            for skill, observed_level in skill_scores.items():
                self.db.add(SkillEvidenceRecord(user_id=attempt.user_id, skill=skill,
                    observed_level=observed_level, confidence=.70, evidence_type="scorecard", analysis_run_id=run.id))
                # Workers may use an autoflush-disabled session; persist the evidence
                # before deriving the projection from its ordered history.
                self.db.flush()
                records=list(self.db.scalars(select(SkillEvidenceRecord).where(
                    SkillEvidenceRecord.user_id==attempt.user_id, SkillEvidenceRecord.skill==skill).order_by(SkillEvidenceRecord.recorded_at.desc()).limit(5)))
                evidence=[SkillEvidence(r.skill,r.observed_level,r.confidence,r.recorded_at,r.evidence_type,r.analysis_run_id) for r in records]
                state=self.db.scalar(select(SkillState).where(SkillState.user_id==attempt.user_id,SkillState.skill==skill))
                current=SkillStateProjection(skill,state.estimated_level,state.confidence,state.updated_at,state.model_version) if state else None
                projection=update_skill_state(current,evidence)
                if state:
                    state.estimated_level, state.confidence, state.model_version=projection.estimated_level, projection.confidence, projection.model_version
                else: self.db.add(SkillState(user_id=attempt.user_id,skill=skill,estimated_level=projection.estimated_level,confidence=projection.confidence,model_version=projection.model_version))
            run.status="completed"; run.current_stage="completed"; attempt.status="completed"; attempt.completed_at=datetime.now(timezone.utc)
            # An assignment is complete only when a worker has completed analysis,
            # never merely when media was uploaded or queued.
            assignment.status="completed"
            self.db.commit()
        except Exception:
            self.db.rollback(); attempt=self.db.get(Attempt,attempt_id); run=self.db.scalar(select(AnalysisRun).where(AnalysisRun.attempt_id==attempt_id).order_by(AnalysisRun.version.desc())); attempt.status="analysis_failed"; run.status="failed"; run.failure_code="analysis_failed"; self.db.commit(); raise
    def _put(self,run,result_type,payload):
        if not self.db.scalar(select(AnalysisResult).where(AnalysisResult.analysis_run_id==run.id,AnalysisResult.result_type==result_type)): self.db.add(AnalysisResult(analysis_run_id=run.id,result_type=result_type,payload=payload)); self.db.commit()
class JobQueue:
    def __init__(self): self.jobs=[]
    def enqueue_attempt_analysis(self,attempt_id): self.jobs.append(attempt_id)
job_queue=JobQueue()
def process_job(db,attempt_id): AnalysisService(db).process(attempt_id)
def owned_attempt(db,user_id,attempt_id):
    item=db.scalar(select(Attempt).where(Attempt.id==attempt_id,Attempt.user_id==user_id))
    if not item: raise DomainError("not_found","Resource not found",404)
    return item


class ActivationService:
    """Durable one-time signup activation workflow.

    The token exists only while the caller constructs the outbound email; the
    database retains its SHA-256 digest as the verification evidence.
    """

    purpose = "signup_activation"

    def __init__(self, db, provider: EmailProvider, *, activation_url_base: str,
                 token_minutes: int, resend_min_seconds: int, resend_max_per_hour: int):
        self.db = db
        self.provider = provider
        self.activation_url_base = activation_url_base
        self.token_minutes = token_minutes
        self.resend_min_seconds = resend_min_seconds
        self.resend_max_per_hour = resend_max_per_hour

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _utc(value: datetime) -> datetime:
        """SQLite omits timezone offsets despite timezone-aware model fields."""
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def _activation_url(self, token: str) -> str:
        return f"{self.activation_url_base}?{urlencode({'token': token})}"

    def issue(self, user: User, *, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        # Signup passes a newly added user. Flush it first so the durable
        # challenge always has a real foreign-key owner in the same transaction.
        self.db.flush()
        active = self.db.scalar(select(EmailVerificationChallenge).where(
            EmailVerificationChallenge.user_id == user.id,
            EmailVerificationChallenge.purpose == self.purpose,
            EmailVerificationChallenge.consumed_at.is_(None),
            EmailVerificationChallenge.invalidated_at.is_(None),
        ).with_for_update())
        if active:
            active.invalidated_at = now
            self.db.flush()
        token = secrets.token_urlsafe(32)
        challenge = EmailVerificationChallenge(
            user_id=user.id,
            purpose=self.purpose,
            token_digest=self._digest(token),
            expires_at=now + timedelta(minutes=self.token_minutes),
        )
        self.db.add(challenge)
        self.db.flush()
        # Send before committing. A provider failure rolls back the newly
        # created user/challenge, avoiding an account that cannot be activated.
        self.provider.send_signup_activation(recipient=user.email, activation_url=self._activation_url(token))

    def may_resend(self, user_id: str, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        recent = list(self.db.scalars(select(EmailVerificationChallenge.created_at).where(
            EmailVerificationChallenge.user_id == user_id,
            EmailVerificationChallenge.purpose == self.purpose,
            EmailVerificationChallenge.created_at >= now - timedelta(hours=1),
        ).order_by(EmailVerificationChallenge.created_at.desc())))
        if len(recent) >= self.resend_max_per_hour:
            return False
        if recent and self._utc(recent[0]) > now - timedelta(seconds=self.resend_min_seconds):
            return False
        return True

    def consume(self, token: str, *, now: datetime | None = None) -> User | None:
        now = now or datetime.now(timezone.utc)
        challenge = self.db.scalar(select(EmailVerificationChallenge).where(
            EmailVerificationChallenge.token_digest == self._digest(token),
        ).with_for_update())
        if not challenge or challenge.consumed_at or challenge.invalidated_at or self._utc(challenge.expires_at) <= now:
            return None
        user = self.db.get(User, challenge.user_id, with_for_update=True)
        if not user:
            return None
        challenge.consumed_at = now
        user.email_verified_at = user.email_verified_at or now
        self.db.commit()
        return user


class DictionaryService:
    """Cache shared lexical reference data without changing user-owned state."""

    payload_version = "dictionary-entry-1"

    def __init__(self, db, provider: DictionaryProvider, *, cache_hours: int):
        self.db = db
        self.provider = provider
        self.cache_hours = cache_hours

    @staticmethod
    def normalize_term(term: str) -> str:
        return " ".join(term.split()).casefold()

    def lookup(self, term: str, *, language: str = "en", now: datetime | None = None) -> DictionaryEntry | None:
        now = now or datetime.now(timezone.utc)
        normalized = self.normalize_term(term)
        entry = self.db.scalar(select(DictionaryEntry).where(
            DictionaryEntry.language == language,
            DictionaryEntry.normalized_term == normalized,
        ))
        if entry and (entry.expires_at is None or ActivationService._utc(entry.expires_at) > now):
            return entry
        try:
            lookup = self.provider.lookup_english(normalized)
        except DictionaryProviderError:
            return entry
        if lookup is None:
            return entry
        expires_at = now + timedelta(hours=self.cache_hours)
        if entry is None:
            entry = DictionaryEntry(
                language=language,
                normalized_term=normalized,
                payload_version=self.payload_version,
                payload=lookup.payload,
                source=lookup.source,
                source_metadata=lookup.source_metadata,
                fetched_at=now,
                expires_at=expires_at,
            )
            self.db.add(entry)
        else:
            entry.payload_version = self.payload_version
            entry.payload = lookup.payload
            entry.source = lookup.source
            entry.source_metadata = lookup.source_metadata
            entry.fetched_at = now
            entry.expires_at = expires_at
        self.db.flush()
        return entry

    def attach_to_vocabulary(self, item: VocabularyItem, *, lookup: bool, language: str = "en") -> None:
        if lookup:
            entry = self.lookup(item.word, language=language)
            if entry:
                item.dictionary_entry_id = entry.id


class CurriculumService:
    """Persistence adapter for the pure V1 baseline/recommendation policy."""

    def __init__(self, db):
        self.db = db

    @staticmethod
    def _candidate_values(candidate: ChallengeCandidate) -> dict:
        return {
            "id": candidate.id,
            "version": 1,
            "prompt": candidate.prompt,
            "preparation_guidance": candidate.preparation_guidance,
            "target_skills": list(candidate.target_skills),
            "target_vocabulary": list(candidate.vocabulary_ids),
            "difficulty": candidate.difficulty.level,
            "target_duration_seconds": candidate.target_duration_seconds,
            "rubric_version": "1",
            "active": candidate.active,
        }

    def _ensure_challenge(self, candidate: ChallengeCandidate) -> Challenge:
        challenge = self.db.get(Challenge, candidate.id)
        if challenge is None:
            challenge = Challenge(**self._candidate_values(candidate))
            self.db.add(challenge)
            self.db.flush()
        return challenge

    def start_baseline(self, user_id: str) -> list[Assignment]:
        """Create the fixed baseline once, or return the persisted sequence."""
        existing = list(self.db.scalars(select(Assignment).where(
            Assignment.user_id == user_id, Assignment.reason == "baseline"
        ).order_by(Assignment.sequence)))
        if existing:
            return self._validate_baseline_set(existing)
        for baseline in baseline_assignments():
            self._ensure_challenge(baseline.challenge)
            self.db.add(Assignment(
                user_id=user_id,
                challenge_id=baseline.challenge.id,
                reason=baseline.reason,
                status="assigned",
                sequence=baseline.sequence,
            ))
        try:
            self.db.commit()
        except IntegrityError as exc:
            # The partial unique indexes added in 20260918_03 make a concurrent
            # create-or-return request safe. Do not translate unrelated database
            # integrity failures into a successful baseline start.
            self.db.rollback()
            if not self._is_baseline_uniqueness_error(exc):
                raise
            recovered = self.baseline_assignments(user_id)
            return self._validate_baseline_set(recovered)
        return self._validate_baseline_set(self.baseline_assignments(user_id))

    @staticmethod
    def _is_baseline_uniqueness_error(exc: IntegrityError) -> bool:
        names = {
            "uq_challenge_assignments_baseline_user_sequence",
            "uq_challenge_assignments_baseline_user_challenge",
        }
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        return constraint_name in names or any(name in str(exc.orig) for name in names)

    @staticmethod
    def _validate_baseline_set(assignments: list[Assignment]) -> list[Assignment]:
        expected = baseline_assignments()
        actual = [(item.sequence, item.challenge_id, item.reason) for item in assignments]
        wanted = [(item.sequence, item.challenge.id, item.reason) for item in expected]
        if actual != wanted:
            raise DomainError(
                "baseline_state_invalid",
                "The stored baseline sequence is incomplete or invalid",
                409,
            )
        return assignments

    def baseline_assignments(self, user_id: str) -> list[Assignment]:
        return list(self.db.scalars(select(Assignment).where(
            Assignment.user_id == user_id, Assignment.reason == "baseline"
        ).order_by(Assignment.sequence)))

    def completed_baseline_ids(self, user_id: str) -> set[str]:
        """Only completed/analyzed attempts advance baseline progress."""
        return set(self.db.scalars(select(Assignment.challenge_id).join(
            Attempt, Attempt.assignment_id == Assignment.id
        ).where(
            Assignment.user_id == user_id,
            Assignment.reason == "baseline",
            Attempt.status == "completed",
        )))

    def baseline_status(self, user_id: str):
        assignments = self.baseline_assignments(user_id)
        if not assignments:
            return "not_started", assignments, None
        completed = self.completed_baseline_ids(user_id)
        progress = baseline_progress(completed)
        if progress.is_complete:
            return "completed", assignments, None
        next_challenge_id = progress.next_assignment.challenge.id
        current = next(item for item in assignments if item.challenge_id == next_challenge_id)
        return "in_progress", assignments, current

    def current_assignment(self, user_id: str) -> Assignment | None:
        status, _, baseline_current = self.baseline_status(user_id)
        if status != "completed":
            return baseline_current
        assigned = self.db.scalar(select(Assignment).where(
            Assignment.user_id == user_id,
            Assignment.reason != "baseline",
            Assignment.status == "assigned",
        ).order_by(Assignment.assigned_at.desc()))
        if assigned:
            return assigned
        skill_levels = {state.skill: state.estimated_level for state in self.db.scalars(
            select(SkillState).where(SkillState.user_id == user_id)
        )}
        recommendation = recommend_after_baseline(
            completed_baseline_challenge_ids=self.completed_baseline_ids(user_id),
            skill_levels=skill_levels,
        )
        self._ensure_challenge(recommendation.challenge)
        assignment = Assignment(
            user_id=user_id,
            challenge_id=recommendation.challenge.id,
            reason="recommended",
            status="assigned",
            sequence=1,
        )
        self.db.add(assignment)
        self.db.commit()
        return assignment
