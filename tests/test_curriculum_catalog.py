from app.personalization.catalog import ACTIVE_CATALOG, BASELINE_CATALOG, PRACTICE_CATALOG
from app.personalization.challenge_engine import ChallengeEngine, ChallengeContext


def test_active_catalog_has_unique_concrete_vocabulary_targets():
    assert len({challenge.id for challenge in ACTIVE_CATALOG}) == len(ACTIVE_CATALOG)
    for challenge in ACTIVE_CATALOG:
        assert challenge.vocabulary_ids
        assert all(not target.startswith("lexicon:") for target in challenge.vocabulary_ids)
        ChallengeEngine().recommend((challenge,), ChallengeContext())


def test_baseline_and_practice_catalogs_remain_separate_learning_stages():
    assert {challenge.id for challenge in BASELINE_CATALOG}.isdisjoint(
        challenge.id for challenge in PRACTICE_CATALOG
    )
