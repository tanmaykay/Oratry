from app.scoring import SCORECARD_VERSION, build_deterministic_scorecard


def test_scorecard_is_versioned_explainable_and_uses_only_measured_inputs():
    card = build_deterministic_scorecard(
        {"words_per_minute": 135, "filler_rate": 1, "duration_seconds": 60},
        immediate_repetitions=("really",), target_duration_seconds=60,
        target_vocabulary=("clarity", "evidence"), used_target_vocabulary=("clarity",),
    )
    assert card["scorecardVersion"] == SCORECARD_VERSION
    assert card["overall"] is not None
    assert card["dimensions"]["pace"]["score"] == 100
    assert card["dimensions"]["target_vocabulary"]["score"] == 50
    assert card["provenance"]["source"] == "deterministic_measurements_only"
    assert "llm_dimension_scores" in card["provenance"]["excluded"]
    assert all("rule" in dimension for dimension in card["dimensions"].values())


def test_missing_measurements_are_unavailable_not_zero_or_a_penalty():
    card = build_deterministic_scorecard({"word_count": 10})
    assert card["overall"] is None
    assert card["coverage"] == {"measuredDimensions": 0, "availableWeight": 0.0}
    assert {item["status"] for item in card["dimensions"].values()} == {"unavailable"}


def test_bounds_and_partial_coverage_are_stable():
    card = build_deterministic_scorecard(
        {"words_per_minute": 500, "filler_rate": 99, "duration_seconds": 1},
        immediate_repetitions=("a",) * 20, target_duration_seconds=100,
        target_vocabulary=("word",), used_target_vocabulary=(),
    )
    assert all(0 <= item["score"] <= 100 for item in card["dimensions"].values() if item["score"] is not None)
    assert 0 <= card["overall"] <= 100


def test_invalid_values_do_not_become_measurements():
    card = build_deterministic_scorecard({"words_per_minute": True, "filler_rate": -1, "duration_seconds": "60"})
    assert card["overall"] is None
