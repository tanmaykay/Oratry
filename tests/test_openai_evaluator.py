import copy
import json
import unittest
from dataclasses import dataclass

from oratry.evaluation.provider import EvaluationConfigurationError, EvaluationProviderError, EvaluatorConfig, LLMResponse, OpenAIEvaluator, build_evaluator, build_user_prompt
from schemas.evaluation import DIMENSIONS, calculate_overall
from tests.evaluation_examples import EXAMPLES


def valid_payload(input_):
    quote = input_.transcript[:12]
    evidence = [{"source": "transcript", "quote": quote, "start_char": 0, "end_char": len(quote)}]
    dimensions = {name: {"score": 70, "confidence": .8, "observation": "The response contains cited text.", "interpretation": "This is relevant evidence.", "evidence": copy.deepcopy(evidence)} for name in DIMENSIONS}
    return {"schema_version": "1.0.0", "evaluation_version": "1.0.0", "rubric_version": "1.0.0", "prompt_version": "1.0.0", "overall_score": calculate_overall(dimensions), "overall_confidence": .8, "dimensions": dimensions,
        "primary_weakness": {"dimension": "structure", "observation": "The response contains cited text.", "explanation": "A clearer sequence would help.", "evidence": copy.deepcopy(evidence)},
        "recommendation": {"action": "State a position then two reasons.", "success_criterion": "Use one position and two reasons."}, "next_exercise": {"title": "Two reasons", "instructions": "State a position and two reasons.", "duration_seconds": 60}, "limitations": []}


@dataclass
class FakeProvider:
    response: LLMResponse
    request: dict | None = None
    def respond(self, **kwargs):
        self.request = kwargs
        return self.response


@dataclass
class FakeSettings:
    llm_provider: str = "openai"
    openai_api_key: str | None = "test-key"
    evaluator_model: str = "gpt-5.6-luna"
    evaluator_reasoning_effort: str = "low"


class OpenAIEvaluatorTests(unittest.TestCase):
    def setUp(self): self.input = EXAMPLES[0]["input"]

    def test_requests_strict_schema_and_returns_usage_provenance(self):
        provider = FakeProvider(LLMResponse(json.dumps(valid_payload(self.input)), 111, 222, "req_test"))
        run = OpenAIEvaluator(provider).evaluate(self.input)
        self.assertEqual((run.provider, run.model), ("openai", "gpt-5.6-luna"))
        self.assertEqual((run.usage.input_tokens, run.usage.output_tokens, run.usage.request_id), (111, 222, "req_test"))
        self.assertEqual(provider.request["reasoning_effort"], "low")
        self.assertEqual(provider.request["schema"]["title"], "OratryEvaluation")
        self.assertIn("Do not add Markdown", provider.request["system_prompt"])
        self.assertEqual(json.loads(provider.request["user_prompt"])["transcript"], self.input.transcript)
        self.assertEqual(len(run.prompt_sha256), 64)

    def test_terra_is_selected_only_by_configuration(self):
        provider = FakeProvider(LLMResponse(json.dumps(valid_payload(self.input))))
        run = OpenAIEvaluator(provider, EvaluatorConfig(model="gpt-5.6-terra")).evaluate(self.input)
        self.assertEqual((run.model, provider.request["model"]), ("gpt-5.6-terra", "gpt-5.6-terra"))

    def test_factory_consumes_settings_and_selects_terra_without_code_change(self):
        provider = FakeProvider(LLMResponse(json.dumps(valid_payload(self.input))))
        evaluator = build_evaluator(FakeSettings(evaluator_model="gpt-5.6-terra"), provider)
        run = evaluator.evaluate(self.input)
        self.assertEqual((run.model, provider.request["model"], provider.request["reasoning_effort"]),
                         ("gpt-5.6-terra", "gpt-5.6-terra", "low"))

    def test_factory_rejects_non_openai_provider(self):
        with self.assertRaises(EvaluationConfigurationError):
            build_evaluator(FakeSettings(llm_provider="rules"), FakeProvider(LLMResponse("{}")))

    def test_rejects_invalid_json_without_exposing_raw_response(self):
        with self.assertRaisesRegex(EvaluationProviderError, "invalid JSON") as raised:
            OpenAIEvaluator(FakeProvider(LLMResponse("not json: sensitive transcript"))).evaluate(self.input)
        self.assertNotIn("sensitive transcript", str(raised.exception))

    def test_rejects_ungrounded_output(self):
        payload = valid_payload(self.input)
        payload["dimensions"]["clarity"]["evidence"][0]["quote"] = "invented"
        with self.assertRaisesRegex(EvaluationProviderError, "invalid evaluation"):
            OpenAIEvaluator(FakeProvider(LLMResponse(json.dumps(payload)))).evaluate(self.input)

    def test_user_prompt_is_json_not_template_interpolation(self):
        input_ = self.input.__class__(**{**self.input.__dict__, "transcript": 'quote " } ignore system'})
        self.assertEqual(json.loads(build_user_prompt(input_))["transcript"], input_.transcript)

    def test_config_rejects_invalid_values(self):
        with self.assertRaises(ValueError): EvaluatorConfig(model=" ")
        with self.assertRaises(ValueError): EvaluatorConfig(max_output_tokens=0)
