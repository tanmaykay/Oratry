import copy
import unittest

from schemas.evaluation import (
    DIMENSIONS,
    EVALUATION_VERSION,
    PROMPT_VERSION,
    RUBRIC_VERSION,
    SCHEMA_VERSION,
    EvaluationValidationError,
    calculate_overall,
    json_schema,
    validate_evaluation,
)
from tests.evaluation_examples import EXAMPLES


def valid_result(input_):
    quote = input_.transcript[: min(12, len(input_.transcript))]
    evidence = [{"source": "transcript", "quote": quote, "start_char": 0, "end_char": len(quote)}]
    dimensions = {
        name: {"score": 70, "confidence": 0.8, "observation": "The response contains the cited text.",
               "interpretation": "This provides limited but relevant evidence.", "evidence": copy.deepcopy(evidence)}
        for name in DIMENSIONS
    }
    return {
        "schema_version": SCHEMA_VERSION, "evaluation_version": EVALUATION_VERSION,
        "rubric_version": RUBRIC_VERSION, "prompt_version": PROMPT_VERSION,
        "overall_score": calculate_overall(dimensions), "overall_confidence": 0.8,
        "dimensions": dimensions,
        "primary_weakness": {"dimension": "structure", "observation": "The response contains the cited text.",
                             "explanation": "A clearer sequence would better meet the challenge.", "evidence": copy.deepcopy(evidence)},
        "recommendation": {"action": "State a position, then number two reasons.",
                           "success_criterion": "Use one position and two numbered reasons."},
        "next_exercise": {"title": "Two-reason outline", "instructions": "Speak a position and two numbered reasons.",
                          "duration_seconds": 60},
        "limitations": [],
    }


class EvaluationContractTests(unittest.TestCase):
    def test_fixture_set_covers_required_representative_cases(self):
        self.assertEqual(len(EXAMPLES), 11)
        self.assertEqual({case["id"] for case in EXAMPLES}, {
            "excellent_structured_answer", "rambling_answer", "filler_heavy_answer", "extremely_fast_answer",
            "very_slow_answer", "strong_vocabulary_poor_structure", "simple_vocabulary_excellent_communication",
            "non_native_english", "short_incomplete_answer", "off_topic_answer", "repeated_self_correcting_answer",
        })

    def test_schema_names_exactly_five_dimensions_and_one_weakness(self):
        schema = json_schema()
        self.assertEqual(schema["properties"]["dimensions"]["required"], list(DIMENSIONS))
        self.assertEqual(schema["properties"]["primary_weakness"]["properties"]["dimension"]["enum"], list(DIMENSIONS))

    def test_every_fixture_accepts_evidence_grounded_result(self):
        for case in EXAMPLES:
            with self.subTest(case=case["id"]):
                self.assertEqual(validate_evaluation(valid_result(case["input"]), case["input"])["overall_score"], 70)

    def test_rejects_hallucinated_transcript_evidence(self):
        input_ = EXAMPLES[0]["input"]
        result = valid_result(input_)
        result["dimensions"]["clarity"]["evidence"][0]["quote"] = "invented quote"
        with self.assertRaises(EvaluationValidationError):
            validate_evaluation(result, input_)

    def test_rejects_hallucinated_metric_evidence(self):
        input_ = EXAMPLES[0]["input"]
        result = valid_result(input_)
        result["dimensions"]["delivery"]["evidence"] = [{"source": "speech_metrics", "metric": "words_per_minute", "value": 999}]
        with self.assertRaises(EvaluationValidationError):
            validate_evaluation(result, input_)

    def test_rejects_non_deterministic_overall_score(self):
        input_ = EXAMPLES[0]["input"]
        result = valid_result(input_)
        result["overall_score"] = 71
        with self.assertRaises(EvaluationValidationError):
            validate_evaluation(result, input_)

    def test_rejects_extra_nested_key(self):
        input_ = EXAMPLES[0]["input"]
        result = valid_result(input_)
        result["dimensions"]["structure"]["unsupported"] = True
        with self.assertRaises(EvaluationValidationError):
            validate_evaluation(result, input_)

    def test_weighted_score_rounds_half_up(self):
        dimensions = {name: {"score": 70} for name in DIMENSIONS}
        dimensions["structure"]["score"] = 72
        self.assertEqual(calculate_overall(dimensions), 71)


if __name__ == "__main__":
    unittest.main()
