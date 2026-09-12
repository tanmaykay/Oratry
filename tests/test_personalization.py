from datetime import datetime, timedelta, timezone
import pytest

from app.personalization.challenge_engine import (
    ChallengeCandidate, ChallengeContext, ChallengeEngine, ChallengeHistory,
    ChallengeValidationError, CognitiveTask, Difficulty,
)
from app.personalization.skill_engine import SkillEvidence, update_skill_state
from app.personalization.vocabulary_engine import VocabularyProgress, VocabularyState, select_vocabulary


NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)
def difficulty(**changes):
    values = dict(topic_familiarity=3, cognitive_complexity=3, preparation_time=3,
                  speaking_time=3, vocabulary_difficulty=3, opposition=2, pressure=2)
    values.update(changes); return Difficulty(**values)
def candidate(id, **changes):
    values = dict(id=id, prompt="Make and support a clear claim.", preparation_guidance="Plan a claim and two reasons.",
                  target_skills=("structure",), difficulty=difficulty(), cognitive_task=CognitiveTask.ARGUE,
                  topic="work", target_duration_seconds=120)
    values.update(changes); return ChallengeCandidate(**values)

def test_recommendation_prioritizes_skill_need_and_explains_choice():
    selected = ChallengeEngine().recommend([candidate("structure"), candidate("delivery", target_skills=("delivery",))],
        ChallengeContext(skill_levels={"structure":25, "delivery":85}, goals=("speak about work",)), NOW)
    assert selected.challenge.id == "structure"
    assert "targets current skill need (structure)" in selected.reasons

def test_invalid_challenges_are_never_generated_or_selected():
    invalid = candidate("bad", preparation_guidance="", target_duration_seconds=5)
    with pytest.raises(ChallengeValidationError, match="No valid"):
        ChallengeEngine().recommend([invalid], ChallengeContext(), NOW)

def test_recency_prevents_repeat_when_a_comparable_candidate_exists():
    history = ChallengeHistory("same", None, CognitiveTask.ARGUE, "work", NOW - timedelta(days=1))
    result = ChallengeEngine().recommend([candidate("same"), candidate("new", cognitive_task=CognitiveTask.COMPARE)],
        ChallengeContext(recent_history=(history,)), NOW)
    assert result.challenge.id == "new"

def test_skill_state_is_evidence_based_and_missing_evidence_does_not_change_it():
    evidence = [SkillEvidence("language", 40, .5, NOW - timedelta(days=1), "evaluation"), SkillEvidence("language", 80, 1, NOW, "evaluation")]
    state = update_skill_state(None, evidence)
    assert state.estimated_level == pytest.approx(66.67)
    assert update_skill_state(state, []) == state

def test_vocabulary_only_advances_and_prefers_retrieval_stage():
    recalled = VocabularyProgress("a", VocabularyState.RECALLED, NOW, "work")
    encountered = VocabularyProgress("b", VocabularyState.ENCOUNTERED, NOW - timedelta(days=5), "work")
    assert select_vocabulary([encountered, recalled], "work")[0].vocabulary_id == "a"
    assert recalled.advance(VocabularyState.USED_CORRECTLY, NOW).state == VocabularyState.USED_CORRECTLY
    with pytest.raises(ValueError): recalled.advance(VocabularyState.RECOGNIZED, NOW)
