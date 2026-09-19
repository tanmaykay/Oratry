"""Pure baseline sequencing and post-baseline assignment policy for V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping

from .catalog import BASELINE_CATALOG, PRACTICE_CATALOG
from .challenge_engine import (
    ChallengeCandidate,
    ChallengeContext,
    ChallengeEngine,
    ChallengeHistory,
    Difficulty,
    Recommendation,
)


BASELINE_POLICY_VERSION = "baseline-rules-1"


@dataclass(frozen=True)
class BaselineAssignment:
    """An ordered, immutable challenge reference for persistence by the backend."""

    sequence: int
    challenge: ChallengeCandidate
    reason: str = "baseline"


@dataclass(frozen=True)
class BaselineProgress:
    assignments: tuple[BaselineAssignment, ...]
    next_assignment: BaselineAssignment | None

    @property
    def is_complete(self) -> bool:
        return self.next_assignment is None


class BaselineIncompleteError(ValueError):
    """Raised when adaptive assignment is requested before baseline completion."""


def baseline_assignments(catalog: Iterable[ChallengeCandidate] = BASELINE_CATALOG) -> tuple[BaselineAssignment, ...]:
    """Return the fixed V1 baseline sequence, rejecting invalid catalog entries."""
    challenges = tuple(catalog)
    if not challenges:
        raise ValueError("Baseline catalog must not be empty")
    # ChallengeEngine validation is the single curriculum-validation authority.
    engine = ChallengeEngine()
    for challenge in challenges:
        engine.recommend((challenge,), ChallengeContext())
    return tuple(BaselineAssignment(sequence=index, challenge=challenge) for index, challenge in enumerate(challenges, start=1))


def baseline_progress(completed_challenge_ids: Iterable[str], catalog: Iterable[ChallengeCandidate] = BASELINE_CATALOG) -> BaselineProgress:
    """Compute resume state from completed assignments; unknown IDs do not advance it."""
    assignments = baseline_assignments(catalog)
    completed = frozenset(completed_challenge_ids)
    next_assignment = next((item for item in assignments if item.challenge.id not in completed), None)
    return BaselineProgress(assignments=assignments, next_assignment=next_assignment)


def recommend_after_baseline(
    *,
    completed_baseline_challenge_ids: Iterable[str],
    skill_levels: Mapping[str, float],
    goals: Iterable[str] = (),
    recent_history: Iterable[ChallengeHistory] = (),
    desired_difficulty: Difficulty | None = None,
    topic_familiarity: Mapping[str, int] | None = None,
    vocabulary_history: Mapping[str, str] | None = None,
    candidates: Iterable[ChallengeCandidate] = PRACTICE_CATALOG,
    now: datetime | None = None,
) -> Recommendation:
    """Select the next approved practice challenge after a completed baseline.

    ``skill_levels`` is a projection derived from recorded analysis evidence. Missing
    skills remain neutral in ``ChallengeEngine``; they are never interpreted as low
    ability. The returned explanation is deterministic and safe to persist as the
    assignment reason detail.
    """
    progress = baseline_progress(completed_baseline_challenge_ids)
    if not progress.is_complete:
        raise BaselineIncompleteError("Complete the baseline before requesting an adaptive assignment")
    context = ChallengeContext(
        goals=tuple(goals), skill_levels=dict(skill_levels), recent_history=tuple(recent_history),
        desired_difficulty=desired_difficulty, topic_familiarity=dict(topic_familiarity or {}),
        vocabulary_history=dict(vocabulary_history or {}),
    )
    return ChallengeEngine().recommend(candidates, context, now)
