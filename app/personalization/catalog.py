"""Versioned, curated curriculum inputs used by the learning policy.

This module deliberately contains data only.  A persistence adapter may copy these
values into the ``challenges`` table, but assignment policy never manufactures a
challenge from user input.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .challenge_engine import ChallengeCandidate, CognitiveTask, Difficulty


CURRICULUM_CATALOG_VERSION = "2026-09-19.1"
"""Version for curated content and taxonomy, independent of policy versions."""


class ChallengeMode(StrEnum):
    """Learning context, deliberately separate from the cognitive task."""

    PREPARED_ARGUMENT = "prepared_argument"
    IMPROMPTU = "impromptu"
    INTERVIEW = "interview"
    EXPLANATION = "explanation"
    DEBATE = "debate"
    STORYTELLING = "storytelling"
    PROFESSIONAL = "professional"
    LEADERSHIP = "leadership"


class TopicFamily(StrEnum):
    TECHNOLOGY = "technology"
    SCIENCE = "science"
    SOCIETY = "society"
    BUSINESS = "business"
    CULTURE = "culture"
    PHILOSOPHY = "philosophy"


@dataclass(frozen=True)
class CuratedChallenge:
    """Curriculum metadata not yet represented by the V1 database schema.

    ``challenge`` remains the assignable, policy-safe object.  The wrapper captures
    future product context without making unfinished modes selectable by V1 routes.
    ``vocabulary_targets`` are stable *catalog lexical IDs*, not user-vocabulary
    primary keys; a later assignment adapter resolves them by normalized lemma.
    """

    challenge: ChallengeCandidate
    mode: ChallengeMode
    topic_family: TopicFamily
    preparation_seconds: int
    vocabulary_targets: tuple[str, ...] = ()
    availability: str = "future"

    def __post_init__(self) -> None:
        if not 0 <= self.preparation_seconds <= 1800:
            raise ValueError("Preparation time must be between 0 and 1800 seconds")
        if self.vocabulary_targets != self.challenge.vocabulary_ids:
            raise ValueError("Vocabulary targets must match the challenge lexical IDs")


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
        target_duration_seconds=60, vocabulary_ids=("decision", "because", "therefore"),
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
        target_duration_seconds=90, vocabulary_ids=("claim", "reason", "conclusion"),
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
        target_duration_seconds=90, vocabulary_ids=("problem", "resolve", "outcome"),
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
        target_duration_seconds=120, vocabulary_ids=("trade-off", "evidence", "outcome"),
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
        target_duration_seconds=120, vocabulary_ids=("compare", "criterion", "recommend"),
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
        topic="work", target_duration_seconds=120, vocabulary_ids=("purpose", "sequence", "practical"), family_id="practice-delivery",
    ),
)


ACTIVE_CATALOG: tuple[ChallengeCandidate, ...] = BASELINE_CATALOG + PRACTICE_CATALOG
"""The production V1 curriculum entries eligible for persistence/assignment."""


# These entries make the approved next curriculum explicit without silently
# widening today's V1 recommendation pool.  They become assignable only when a
# later product slice implements the relevant mode, preparation experience,
# evaluation rubric, and persistence contract.  IDs and lexical IDs are stable.
FUTURE_CURRICULUM: tuple[CuratedChallenge, ...] = (
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="prepared-argument-technology-v1",
            prompt="After independent research, argue whether schools should restrict student use of generative AI.",
            preparation_guidance="Form a position, then use claim, evidence, explanation, and conclusion. Do not use AI to formulate your response.",
            target_skills=("thinking", "structure", "language"),
            difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=4, preparation_time=4,
                                   speaking_time=4, vocabulary_difficulty=3, opposition=3, pressure=2),
            cognitive_task=CognitiveTask.ARGUE, topic="generative AI in education",
            target_duration_seconds=180, vocabulary_ids=("lexicon:nuance", "lexicon:mitigate", "lexicon:conventional"),
            active=False, family_id="prepared-argument-technology",
        ),
        mode=ChallengeMode.PREPARED_ARGUMENT, topic_family=TopicFamily.TECHNOLOGY,
        preparation_seconds=600, vocabulary_targets=("lexicon:nuance", "lexicon:mitigate", "lexicon:conventional"),
    ),
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="impromptu-science-v1",
            prompt="You have 30 seconds to prepare: explain why scientific uncertainty can still support a practical decision.",
            preparation_guidance="State the idea simply, give one example, and close with a practical implication.",
            target_skills=("thinking", "fluency", "language"),
            difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=3, preparation_time=5,
                                   speaking_time=3, vocabulary_difficulty=2, opposition=1, pressure=4),
            cognitive_task=CognitiveTask.IMPROMPTU, topic="scientific uncertainty",
            target_duration_seconds=90, vocabulary_ids=("lexicon:evidence", "lexicon:probability"),
            active=False, family_id="impromptu-science",
        ),
        mode=ChallengeMode.IMPROMPTU, topic_family=TopicFamily.SCIENCE,
        preparation_seconds=30, vocabulary_targets=("lexicon:evidence", "lexicon:probability"),
    ),
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="interview-business-v1",
            prompt="In an interview, describe a time you improved a process despite limited time or resources.",
            preparation_guidance="Use situation, task, action, and result. Make your individual contribution clear.",
            target_skills=("structure", "language", "delivery"),
            difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=3, preparation_time=3,
                                   speaking_time=4, vocabulary_difficulty=3, opposition=2, pressure=4),
            cognitive_task=CognitiveTask.STORY, topic="professional problem solving",
            target_duration_seconds=150, vocabulary_ids=("lexicon:initiative", "lexicon:constraint", "lexicon:outcome"),
            active=False, family_id="interview-business",
        ),
        mode=ChallengeMode.INTERVIEW, topic_family=TopicFamily.BUSINESS,
        preparation_seconds=120, vocabulary_targets=("lexicon:initiative", "lexicon:constraint", "lexicon:outcome"),
    ),
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="explanation-science-v1",
            prompt="Explain how vaccines train an immune system to a curious teenager without assuming prior knowledge.",
            preparation_guidance="Define the central idea, use a concrete analogy carefully, then explain one limitation.",
            target_skills=("thinking", "structure", "language"),
            difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=3, preparation_time=3,
                                   speaking_time=3, vocabulary_difficulty=3, opposition=1, pressure=2),
            cognitive_task=CognitiveTask.EXPLAIN, topic="immunology",
            target_duration_seconds=120, vocabulary_ids=("lexicon:immune", "lexicon:response", "lexicon:protection"),
            active=False, family_id="explanation-science",
        ),
        mode=ChallengeMode.EXPLANATION, topic_family=TopicFamily.SCIENCE,
        preparation_seconds=180, vocabulary_targets=("lexicon:immune", "lexicon:response", "lexicon:protection"),
    ),
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="debate-society-v1",
            prompt="Argue against the view that social-media platforms should be responsible for every harmful post they host.",
            preparation_guidance="Steelman the other side first, then make two distinct arguments and acknowledge a trade-off.",
            target_skills=("thinking", "structure", "language"),
            difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=5, preparation_time=4,
                                   speaking_time=4, vocabulary_difficulty=4, opposition=5, pressure=3),
            cognitive_task=CognitiveTask.OPPOSE, topic="platform responsibility",
            target_duration_seconds=180, vocabulary_ids=("lexicon:accountability", "lexicon:proportional", "lexicon:consequence"),
            active=False, family_id="debate-society",
        ),
        mode=ChallengeMode.DEBATE, topic_family=TopicFamily.SOCIETY,
        preparation_seconds=300, vocabulary_targets=("lexicon:accountability", "lexicon:proportional", "lexicon:consequence"),
    ),
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="storytelling-culture-v1",
            prompt="Tell a story about a tradition, object, or place that changed how you see your community.",
            preparation_guidance="Set the scene, introduce a moment of change, then make the meaning explicit at the end.",
            target_skills=("structure", "fluency", "delivery"),
            difficulty=_difficulty(topic_familiarity=2, cognitive_complexity=3, preparation_time=3,
                                   speaking_time=4, vocabulary_difficulty=3, opposition=1, pressure=2),
            cognitive_task=CognitiveTask.STORY, topic="cultural memory",
            target_duration_seconds=150, vocabulary_ids=("lexicon:heritage", "lexicon:perspective", "lexicon:significance"),
            active=False, family_id="storytelling-culture",
        ),
        mode=ChallengeMode.STORYTELLING, topic_family=TopicFamily.CULTURE,
        preparation_seconds=180, vocabulary_targets=("lexicon:heritage", "lexicon:perspective", "lexicon:significance"),
    ),
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="professional-business-v1",
            prompt="Recommend a small, measurable change that would improve a team handoff between two departments.",
            preparation_guidance="State the current friction, propose the change, describe its benefit, and name one risk.",
            target_skills=("thinking", "structure", "delivery"),
            difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=4, preparation_time=3,
                                   speaking_time=3, vocabulary_difficulty=3, opposition=2, pressure=3),
            cognitive_task=CognitiveTask.PERSUADE, topic="cross-functional collaboration",
            target_duration_seconds=120, vocabulary_ids=("lexicon:alignment", "lexicon:stakeholder", "lexicon:efficient"),
            active=False, family_id="professional-business",
        ),
        mode=ChallengeMode.PROFESSIONAL, topic_family=TopicFamily.BUSINESS,
        preparation_seconds=120, vocabulary_targets=("lexicon:alignment", "lexicon:stakeholder", "lexicon:efficient"),
    ),
    CuratedChallenge(
        challenge=ChallengeCandidate(
            id="leadership-philosophy-v1",
            prompt="Address a team after an ethical mistake. Explain what happened, what changes now, and how you will rebuild trust.",
            preparation_guidance="Take responsibility without speculation, name a concrete next action, and end with a clear standard.",
            target_skills=("thinking", "structure", "delivery"),
            difficulty=_difficulty(topic_familiarity=3, cognitive_complexity=5, preparation_time=3,
                                   speaking_time=4, vocabulary_difficulty=4, opposition=3, pressure=4),
            cognitive_task=CognitiveTask.PERSUADE, topic="ethical leadership",
            target_duration_seconds=180, vocabulary_ids=("lexicon:integrity", "lexicon:accountability", "lexicon:principle"),
            active=False, family_id="leadership-philosophy",
        ),
        mode=ChallengeMode.LEADERSHIP, topic_family=TopicFamily.PHILOSOPHY,
        preparation_seconds=120, vocabulary_targets=("lexicon:integrity", "lexicon:accountability", "lexicon:principle"),
    ),
)


def future_challenges_for_mode(mode: ChallengeMode) -> tuple[CuratedChallenge, ...]:
    """Return a stable catalog view for planning; never use it as a V1 selector."""
    return tuple(entry for entry in FUTURE_CURRICULUM if entry.mode is mode)
