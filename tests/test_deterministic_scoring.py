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
    assert card["coverage"] == {"measuredDimensions": 0, "availableWeight": 0.0, "responseCoverageCap": None}
    assert {item["status"] for item in card["dimensions"].values()} == {"unavailable"}


def test_bounds_and_partial_coverage_are_stable():
    card = build_deterministic_scorecard(
        {"words_per_minute": 500, "filler_rate": 99, "duration_seconds": 1},
        immediate_repetitions=("a",) * 20, target_duration_seconds=100,
        target_vocabulary=("word",), used_target_vocabulary=(),
    )
    assert all(0 <= item["score"] <= 100 for item in card["dimensions"].values() if item["score"] is not None)
    assert 0 <= card["overall"] <= 100


def test_silence_scores_zero_instead_of_receiving_credit_for_clean_delivery_metrics():
    card = build_deterministic_scorecard(
        {"word_count": 0, "words_per_minute": 0, "filler_rate": 0, "duration_seconds": 15},
        immediate_repetitions=(), target_duration_seconds=120,
    )
    assert card["dimensions"]["response_coverage"]["score"] == 0
    assert card["overall"] == 0


def test_short_response_is_capped_by_challenge_relative_transcript_coverage():
    card = build_deterministic_scorecard(
        {"word_count": 10, "words_per_minute": 135, "filler_rate": 0, "duration_seconds": 120},
        immediate_repetitions=(), target_duration_seconds=120,
    )
    assert card["dimensions"]["response_coverage"]["input"] == {"word_count": 10.0, "minimum_word_count": 60}
    assert card["overall"] <= 17


def test_long_internal_pauses_reduce_fluency_score_without_penalizing_brief_pauses():
    card = build_deterministic_scorecard(
        {"word_count": 100, "words_per_minute": 135, "filler_rate": 0,
         "duration_seconds": 60, "long_pause_seconds": 18},
        immediate_repetitions=(), target_duration_seconds=60,
    )
    assert card["dimensions"]["pausing"]["input"]["long_pause_ratio"] == 0.3
    assert card["dimensions"]["pausing"]["score"] < 40


def test_invalid_values_do_not_become_measurements():
    card = build_deterministic_scorecard({"words_per_minute": True, "filler_rate": -1, "duration_seconds": "60"})
    assert card["overall"] is None
