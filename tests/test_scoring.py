from app.services import score
def test_weighted_score_is_deterministic_and_versioned():
    result=score({"structure":80,"clarity":70,"fluency":60,"language":50,"delivery":40})
    assert result["overall"] == 62
    assert result["scorerVersion"] == "1"
    assert result["weights"]["structure"] == .25
