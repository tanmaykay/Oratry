"""Versioned, curated curriculum inputs used by the V1 learning policy.

This module deliberately contains data only.  A persistence adapter may copy these
values into the ``challenges`` table, but assignment policy never manufactures a
challenge from user input.
"""
from __future__ import annotations

from .challenge_engine import ChallengeCandidate, CognitiveTask, Difficulty


def _difficulty(**values: int) -> Difficulty:
    return Difficulty(
        topic_familiarity=values["topic_familiarity"],
        cognitive_complexity=values["cognitive_complexity"],
        preparation_time=values["preparation_time"],
        speaking_time=values["speaking_time"],
        vocabulary_difficulty=values["vocabulary_difficulty"],
        opposition=values["opposition"],
        pressure=values["pressure"],
    )


# IDs are immutable curriculum/version identifiers.  Existing attempts must retain
# the challenge snapshot/version they were assigned even if a later catalog changes.
BASELINE_CATALOG: tuple[ChallengeCandidate, ...] = (
    ChallengeCandidate(
        id="baseline-clarity-v1",
        prompt="Explain a routine decision you made recently and why you made it.",
        preparation_guidance="Choose one decision. State it first, then give two reasons and a conclusion.",
        target_skills=("thinking", "language"),
        difficulty=_difficulty(topic_familiarity=1, cognitive_complexity=1, preparation_time=2,
                               speaking_time=2, vocabulary_difficulty=1, opposition=1, pressure=1),
        cognitive_task=CognitiveTask.EXPLAIN,
        topic="everyday decisions",
        target_duration_seconds=60,
        family_id="baseline-clarity",
    ),
    ChallengeCandidate(
        id="baseline-structure-v1",
        prompt="Make a case for one practical improvement at work, school, or in your community.",
        preparation_guidance="Prepare a clear claim, two supporting reasons, and a short conclusion.",
        target_skills=("thinking", "structure", "language"),
        difficulty=_difficulty(topic_familiarity=2, cognitive_complexity=2, preparation_time=2,
                               speaking_time=3, vocabulary_difficulty=2, opposition=1, pressure=2),
        cognitive_task=CognitiveTask.ARGUE,
        topic="practical improvement",
        target_duration_seconds=90,
        family_id="baseline-structure",
    ),
    ChallengeCandidate(
        id="baseline-delivery-v1",
        prompt="Tell a short story about solving an unexpected problem.",
        preparation_guidance="Use a beginning, a turning point, and an ending. Focus on being understandable.",
        target_skills=("fluency", "delivery"),
        difficulty=_difficulty(topic_familiarity=2, cognitive_complexity=2, preparation_time=2,
                               speaking_time=3, vocabulary_difficulty=1, opposition=1, pressure=2),
        cognitive_task=CognitiveTask.STORY,
        topic="problem solving",
        target_duration_seconds=90,
        family_id="baseline-delivery",
    ),
)


# This deliberately small catalog is enough to exercise adaptive selection after
# baseline. Additional approved curriculum entries can be appended without changing
# policy code.
PRACTICE_CATALOG: tuple[ChallengeCandidate, ...] = (
    ChallengeCandidate(
        id="practice-structure-v1",
        prompt="Argue for a change that would make a familiar process work better.",
        preparation_guidance="State your position, present two reasons in order, then close with the outcome.",
        target_skills=("thinking", "structure"),
        difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=3, preparation_time=3,
                               speaking_time=3, vocabulary_difficulty=2, opposition=2, pressure=2),
        cognitive_task=CognitiveTask.ARGUE,
        topic="practical improvement",
        target_duration_seconds=120,
        family_id="practice-structure",
    ),
    ChallengeCandidate(
        id="practice-fluency-v1",
        prompt="Compare two ways of spending a free afternoon and recommend one.",
        preparation_guidance="Name the options, compare them on two criteria, then make a recommendation.",
        target_skills=("fluency", "language"),
        difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=3, preparation_time=2,
                               speaking_time=3, vocabulary_difficulty=2, opposition=1, pressure=3),
        cognitive_task=CognitiveTask.COMPARE,
        topic="leisure choices",
        target_duration_seconds=120,
        family_id="practice-fluency",
    ),
    ChallengeCandidate(
        id="practice-delivery-v1",
        prompt="Explain how you would introduce a new teammate to a process you know.",
        preparation_guidance="Give the purpose, three steps, and one practical tip. Pause between steps.",
        target_skills=("delivery", "language"),
        difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=2, preparation_time=2,
                               speaking_time=3, vocabulary_difficulty=2, opposition=1, pressure=2),
        cognitive_task=CognitiveTask.EXPLAIN,
        topic="work", target_duration_seconds=120, family_id="practice-delivery",
    ),
)
