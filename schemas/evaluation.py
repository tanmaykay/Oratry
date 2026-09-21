"""Versioned, dependency-free contract and validator for LLM evaluations.

The model is asked only for this JSON shape.  ``validate_evaluation`` performs
post-provider validation against the exact transcript and metrics supplied to
the model, so an otherwise valid JSON response cannot cite invented evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Mapping, Sequence


EVALUATION_VERSION = "1.0.0"
SCHEMA_VERSION = "1.0.0"
RUBRIC_VERSION = "1.0.0"
PROMPT_VERSION = "1.0.0"
SCORER_VERSION = "1.0.0"
DIMENSIONS = ("structure", "clarity", "fluency", "language", "delivery")
WEIGHTS = {
    "structure": Decimal("0.25"),
    "clarity": Decimal("0.20"),
    "fluency": Decimal("0.20"),
    "language": Decimal("0.20"),
    "delivery": Decimal("0.15"),
}


class EvaluationValidationError(ValueError):
    """The provider result is malformed or unsupported by its input."""


@dataclass(frozen=True)
class EvaluationInput:
    challenge: str
    prompt: str
    target_skill: str
    transcript: str
    speech_metrics: Mapping[str, Any]
    target_vocabulary: Sequence[str]
    previous_performance: Mapping[str, Any] | None = None
    user_skill_profile: Mapping[str, Any] | None = None


def json_schema() -> dict[str, Any]:
    """Return the provider-facing JSON Schema (draft 2020-12 compatible)."""
    evidence = {
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "quote", "start_char", "end_char"],
                "properties": {
                    "source": {"const": "transcript"},
                    "quote": {"type": "string", "minLength": 1},
                    "start_char": {"type": "integer", "minimum": 0},
                    "end_char": {"type": "integer", "minimum": 1},
                },
            },
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["source", "metric", "value"],
                "properties": {
                    "source": {"const": "speech_metrics"},
                    "metric": {"type": "string", "minLength": 1},
                    "value": {"type": ["number", "string", "boolean"]},
                },
            },
        ]
    }
    dimension = {
        "type": "object", "additionalProperties": False,
        "required": ["score", "confidence", "observation", "interpretation", "evidence"],
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "observation": {"type": "string", "minLength": 1, "maxLength": 400},
            "interpretation": {"type": "string", "minLength": 1, "maxLength": 400},
            "evidence": {"type": "array", "minItems": 1, "maxItems": 3, "items": evidence},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "OratryEvaluation", "type": "object", "additionalProperties": False,
        "required": ["schema_version", "evaluation_version", "rubric_version", "prompt_version", "overall_score", "overall_confidence",
                     "dimensions", "primary_weakness", "recommendation", "next_exercise", "limitations"],
        "properties": {
            "schema_version": {"const": SCHEMA_VERSION},
            "evaluation_version": {"const": EVALUATION_VERSION},
            "rubric_version": {"const": RUBRIC_VERSION},
            "prompt_version": {"const": PROMPT_VERSION},
            "overall_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "overall_confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "dimensions": {
                "type": "object", "additionalProperties": False, "required": list(DIMENSIONS),
                "properties": {name: dimension for name in DIMENSIONS},
            },
            "primary_weakness": {
                "type": "object", "additionalProperties": False,
                "required": ["dimension", "observation", "explanation", "evidence"],
                "properties": {"dimension": {"enum": list(DIMENSIONS)},
                               "observation": {"type": "string", "minLength": 1, "maxLength": 400},
                               "explanation": {"type": "string", "minLength": 1, "maxLength": 400},
                               "evidence": {"type": "array", "minItems": 1, "maxItems": 3, "items": evidence}},
            },
            "recommendation": {
                "type": "object", "additionalProperties": False,
                "required": ["action", "success_criterion"],
                "properties": {"action": {"type": "string", "minLength": 1, "maxLength": 400},
                               "success_criterion": {"type": "string", "minLength": 1, "maxLength": 300}},
            },
            "next_exercise": {
                "type": "object", "additionalProperties": False,
                "required": ["title", "instructions", "duration_seconds"],
                "properties": {"title": {"type": "string", "minLength": 1, "maxLength": 100},
                               "instructions": {"type": "string", "minLength": 1, "maxLength": 500},
                               "duration_seconds": {"type": "integer", "minimum": 15, "maximum": 600}},
            },
            "limitations": {"type": "array", "maxItems": 3, "items": {"type": "string", "maxLength": 240}},
        },
    }


def calculate_overall(dimensions: Mapping[str, Mapping[str, Any]]) -> int:
    """Published deterministic weighted score, rounded half up to an integer."""
    total = sum(Decimal(str(dimensions[name]["score"])) * WEIGHTS[name] for name in DIMENSIONS)
    return int(total.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _fail(message: str) -> None:
    raise EvaluationValidationError(message)


def _text(value: Any, path: str, maximum: int) -> None:
    if not isinstance(value, str) or not value or len(value) > maximum:
        _fail(f"{path} must be a non-empty string no longer than {maximum} characters")


def _validate_evidence(evidence: Sequence[Mapping[str, Any]], input_: EvaluationInput, path: str) -> None:
    if not evidence or len(evidence) > 3:
        _fail(f"{path} must contain 1 to 3 evidence items")
    for index, item in enumerate(evidence):
        item_path = f"{path}[{index}]"
        if item.get("source") == "transcript":
            if set(item) != {"source", "quote", "start_char", "end_char"}:
                _fail(f"{item_path} has invalid keys")
            start, end, quote = item.get("start_char"), item.get("end_char"), item.get("quote")
            if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int)
                    or not isinstance(end, int) or not 0 <= start < end <= len(input_.transcript)):
                _fail(f"{item_path} has invalid transcript offsets")
            if not isinstance(quote, str) or input_.transcript[start:end] != quote:
                _fail(f"{item_path} quote does not match transcript offsets")
        elif item.get("source") == "speech_metrics":
            if set(item) != {"source", "metric", "value"}:
                _fail(f"{item_path} has invalid keys")
            metric, value = item.get("metric"), item.get("value")
            if metric not in input_.speech_metrics:
                _fail(f"{item_path} references unavailable metric {metric!r}")
            if input_.speech_metrics[metric] != value:
                _fail(f"{item_path} value does not match metric {metric!r}")
        else:
            _fail(f"{item_path} source must be transcript or speech_metrics")


def validate_evaluation(result: Mapping[str, Any], input_: EvaluationInput) -> dict[str, Any]:
    """Validate shape, bounds, exact evidence, and deterministic total.

    Callers may deterministically canonicalize a unique verbatim transcript
    coordinate before this boundary; all semantic and ambiguous evidence is
    rejected rather than repaired.
    """
    required = set(json_schema()["required"])
    if set(result) != required:
        _fail("result keys must exactly match the evaluation schema")
    if (result["schema_version"] != SCHEMA_VERSION or result["evaluation_version"] != EVALUATION_VERSION
            or result["rubric_version"] != RUBRIC_VERSION or result["prompt_version"] != PROMPT_VERSION):
        _fail("unsupported schema, evaluation, rubric, or prompt version")
    for key in ("overall_score",):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or not 0 <= result[key] <= 100:
            _fail(f"{key} must be an integer from 0 to 100")
    if (isinstance(result["overall_confidence"], bool) or not isinstance(result["overall_confidence"], (int, float))
            or not 0 <= result["overall_confidence"] <= 1):
        _fail("overall_confidence must be from 0 to 1")
    dimensions = result["dimensions"]
    if set(dimensions) != set(DIMENSIONS):
        _fail("dimensions must contain exactly the five core dimensions")
    for name in DIMENSIONS:
        dimension = dimensions[name]
        if set(dimension) != {"score", "confidence", "observation", "interpretation", "evidence"}:
            _fail(f"dimensions.{name} has invalid keys")
        if isinstance(dimension["score"], bool) or not isinstance(dimension["score"], int) or not 0 <= dimension["score"] <= 100:
            _fail(f"dimensions.{name}.score must be an integer from 0 to 100")
        if (isinstance(dimension["confidence"], bool) or not isinstance(dimension["confidence"], (int, float))
                or not 0 <= dimension["confidence"] <= 1):
            _fail(f"dimensions.{name}.confidence must be from 0 to 1")
        _text(dimension["observation"], f"dimensions.{name}.observation", 400)
        _text(dimension["interpretation"], f"dimensions.{name}.interpretation", 400)
        _validate_evidence(dimension["evidence"], input_, f"dimensions.{name}.evidence")
    if result["overall_score"] != calculate_overall(dimensions):
        _fail("overall_score must equal the published weighted calculation")
    weakness = result["primary_weakness"]
    if set(weakness) != {"dimension", "observation", "explanation", "evidence"} or weakness["dimension"] not in DIMENSIONS:
        _fail("primary_weakness must identify one valid dimension")
    _text(weakness["observation"], "primary_weakness.observation", 400)
    _text(weakness["explanation"], "primary_weakness.explanation", 400)
    _validate_evidence(weakness["evidence"], input_, "primary_weakness.evidence")
    if set(result["recommendation"]) != {"action", "success_criterion"}:
        _fail("recommendation must contain only action and success_criterion")
    _text(result["recommendation"]["action"], "recommendation.action", 400)
    _text(result["recommendation"]["success_criterion"], "recommendation.success_criterion", 300)
    if set(result["next_exercise"]) != {"title", "instructions", "duration_seconds"}:
        _fail("next_exercise has invalid keys")
    _text(result["next_exercise"]["title"], "next_exercise.title", 100)
    _text(result["next_exercise"]["instructions"], "next_exercise.instructions", 500)
    if (isinstance(result["next_exercise"]["duration_seconds"], bool)
            or not isinstance(result["next_exercise"]["duration_seconds"], int)
            or not 15 <= result["next_exercise"]["duration_seconds"] <= 600):
        _fail("next_exercise.duration_seconds must be from 15 to 600")
    if not isinstance(result["limitations"], list) or len(result["limitations"]) > 3:
        _fail("limitations must be an array with at most 3 items")
    for index, limitation in enumerate(result["limitations"]):
        _text(limitation, f"limitations[{index}]", 240)
    return dict(result)
