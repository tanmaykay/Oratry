from datetime import datetime, timezone
from sqlalchemy import select
from app.core import DomainError
from app.models import AnalysisResult, AnalysisRun, Assignment, Attempt, Challenge, SkillEvidence as SkillEvidenceRecord, SkillState
from app.personalization.skill_engine import SkillEvidence, SkillStateProjection, update_skill_state
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
            run.status="completed"; run.current_stage="completed"; attempt.status="completed"; attempt.completed_at=datetime.now(timezone.utc); self.db.commit()
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
