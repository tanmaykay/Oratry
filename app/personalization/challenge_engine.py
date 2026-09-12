"""Rule-based challenge validation and selection for Oratry V1."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Iterable


class CognitiveTask(StrEnum):
    EXPLAIN = "explain"; ARGUE = "argue"; OPPOSE = "oppose"; COMPARE = "compare"
    PERSUADE = "persuade"; SYNTHESIZE = "synthesize"; STORY = "story"; IMPROMPTU = "impromptu"


class ChallengeValidationError(ValueError):
    """Raised when a challenge cannot safely be assigned."""


DIMENSIONS = ("topic_familiarity", "cognitive_complexity", "preparation_time",
              "speaking_time", "vocabulary_difficulty", "opposition", "pressure")
CORE_SKILLS = frozenset({"thinking", "structure", "language", "fluency", "delivery"})


@dataclass(frozen=True)
class Difficulty:
    """All dimensions are deliberately explicit, bounded 1 (low) through 5 (high)."""
    topic_familiarity: int
    cognitive_complexity: int
    preparation_time: int
    speaking_time: int
    vocabulary_difficulty: int
    opposition: int
    pressure: int

    def __post_init__(self):
        invalid = [name for name in DIMENSIONS if not 1 <= getattr(self, name) <= 5]
        if invalid:
            raise ChallengeValidationError(f"Difficulty dimensions must be between 1 and 5: {', '.join(invalid)}")

    @property
    def level(self) -> int:
        return round(sum(getattr(self, name) for name in DIMENSIONS) / len(DIMENSIONS))


@dataclass(frozen=True)
class ChallengeCandidate:
    id: str
    prompt: str
    preparation_guidance: str
    target_skills: tuple[str, ...]
    difficulty: Difficulty
    cognitive_task: CognitiveTask
    topic: str
    target_duration_seconds: int
    vocabulary_ids: tuple[str, ...] = ()
    active: bool = True
    family_id: str | None = None


@dataclass(frozen=True)
class ChallengeHistory:
    challenge_id: str
    family_id: str | None
    cognitive_task: CognitiveTask
    topic: str
    completed_at: datetime


@dataclass(frozen=True)
class ChallengeContext:
    goals: tuple[str, ...] = ()
    skill_levels: dict[str, float] = field(default_factory=dict)
    recent_history: tuple[ChallengeHistory, ...] = ()
    desired_difficulty: Difficulty | None = None
    topic_familiarity: dict[str, int] = field(default_factory=dict)
    vocabulary_history: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Recommendation:
    challenge: ChallengeCandidate
    score: float
    reasons: tuple[str, ...]


def validate_challenge(challenge: ChallengeCandidate) -> None:
    if not challenge.active: raise ChallengeValidationError("Inactive challenges cannot be assigned")
    if not challenge.id.strip() or not challenge.prompt.strip(): raise ChallengeValidationError("Challenge requires an id and prompt")
    if not challenge.preparation_guidance.strip(): raise ChallengeValidationError("Challenge requires preparation guidance")
    if not challenge.topic.strip(): raise ChallengeValidationError("Challenge requires a topic")
    if not challenge.target_skills or not set(challenge.target_skills) <= CORE_SKILLS:
        raise ChallengeValidationError("Challenge must target one or more core skills")
    if not 15 <= challenge.target_duration_seconds <= 1800:
        raise ChallengeValidationError("Speaking time must be between 15 and 1800 seconds")
    if challenge.difficulty.speaking_time >= 4 and challenge.target_duration_seconds < 90:
        raise ChallengeValidationError("High speaking-time difficulty requires at least 90 seconds")
    if challenge.cognitive_task is CognitiveTask.OPPOSE and challenge.difficulty.opposition < 2:
        raise ChallengeValidationError("Oppose challenges require meaningful opposition")


class ChallengeEngine:
    """Ranks a supplied curriculum; it never invents a question from arbitrary text."""
    model_version = "rules-1"

    def recommend(self, candidates: Iterable[ChallengeCandidate], context: ChallengeContext, now: datetime | None = None) -> Recommendation:
        now = now or datetime.now(timezone.utc)
        ranked: list[Recommendation] = []
        for candidate in candidates:
            try: validate_challenge(candidate)
            except ChallengeValidationError: continue
            score, reasons = self._score(candidate, context, now)
            ranked.append(Recommendation(candidate, score, tuple(reasons)))
        if not ranked: raise ChallengeValidationError("No valid challenge is available")
        return sorted(ranked, key=lambda item: (-item.score, item.challenge.id))[0]

    def _score(self, c: ChallengeCandidate, x: ChallengeContext, now: datetime) -> tuple[float, list[str]]:
        reasons: list[str] = []
        # Skill need (40): lower estimated skill means higher need.
        need = sum(100 - x.skill_levels.get(skill, 50) for skill in c.target_skills) / len(c.target_skills)
        score = need * .40
        reasons.append(f"targets current skill need ({', '.join(c.target_skills)})")
        goals = " ".join(x.goals).lower(); relevance = 100 if c.topic.lower() in goals else (55 if any(word in goals for word in c.topic.lower().split()) else 25)
        score += relevance * .20
        if relevance >= 55: reasons.append("matches a stated goal")
        desired = x.desired_difficulty
        if desired:
            distance = sum(abs(getattr(c.difficulty, d) - getattr(desired, d)) for d in DIMENSIONS)
            fit = max(0, 100 - distance * 10)
        else: fit = 60
        familiarity = x.topic_familiarity.get(c.topic, 3)
        # A familiar topic can sustain more cognitive load; an unfamiliar topic should
        # be assigned only when the challenge deliberately reduces the other demands.
        familiarity_fit = 100 - abs(c.difficulty.topic_familiarity - familiarity) * 25
        fit = (fit * .75) + (max(0, familiarity_fit) * .25)
        score += fit * .18
        if fit >= 70: reasons.append("fits the intended multidimensional difficulty")
        # Variety (12) and recency (5) punish repetitions, especially in the last 7 days.
        recent = [h for h in x.recent_history if h.completed_at >= now - timedelta(days=14)]
        repeated = any(h.challenge_id == c.id or (c.family_id and h.family_id == c.family_id) for h in recent)
        same_task = sum(h.cognitive_task == c.cognitive_task for h in recent[-3:])
        score += 0 if repeated else 12
        score += max(0, 5 - same_task * 2.5)
        if not repeated: reasons.append("avoids recently repeated material")
        # Vocabulary relevance (5): favor words not yet spontaneous, never require unknown words.
        relevant = [word for word in c.vocabulary_ids if x.vocabulary_history.get(word) not in {"used_spontaneously", "used_naturally"}]
        score += min(5, len(relevant) * 2.5)
        if relevant: reasons.append("practices vocabulary still in progress")
        return score, reasons
