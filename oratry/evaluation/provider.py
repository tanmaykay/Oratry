"""OpenAI adapter for the canonical, validated Oratry evaluation contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from schemas.evaluation import EVALUATION_VERSION, PROMPT_VERSION, RUBRIC_VERSION, SCHEMA_VERSION, EvaluationInput, EvaluationValidationError, calculate_overall, json_schema, validate_evaluation

_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "evaluation" / "system.md"


class EvaluationProviderError(RuntimeError):
    """Provider output could not safely become an evaluation; raw output is excluded."""


class EvaluationConfigurationError(ValueError):
    """Configured evaluator provider cannot be safely constructed."""


@dataclass(frozen=True)
class EvaluatorConfig:
    """Application-supplied configuration; model selection is not business logic."""
    model: str = "gpt-5.6-luna"
    reasoning_effort: str = "low"
    max_output_tokens: int = 2_000

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.reasoning_effort.strip() or self.max_output_tokens <= 0:
            raise ValueError("evaluator model/reasoning effort must be non-blank and output tokens positive")


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    request_id: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    output_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None


class LLMProvider(Protocol):
    """Infrastructure port; implementations must enforce strict JSON schema mode."""
    def respond(self, *, model: str, reasoning_effort: str, system_prompt: str, user_prompt: str, schema: Mapping[str, Any], max_output_tokens: int) -> LLMResponse: ...


class EvaluatorSettings(Protocol):
    """The narrow portion of application settings needed by evaluator wiring."""
    llm_provider: str
    openai_api_key: str | None
    gemini_api_key: str | None
    gemini_evaluator_model: str
    evaluator_model: str
    evaluator_reasoning_effort: str


@dataclass(frozen=True)
class EvaluationRun:
    """Validated result and immutable provenance for integration to persist."""
    evaluation: dict[str, Any]
    provider: str
    model: str
    schema_version: str
    evaluation_version: str
    rubric_version: str
    prompt_version: str
    prompt_sha256: str
    usage: LLMUsage


def load_system_prompt() -> str:
    return _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()


def build_user_prompt(input_: EvaluationInput) -> str:
    """A canonical JSON document, rather than unescaped template interpolation."""
    return json.dumps(asdict(input_), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _canonicalize_unique_transcript_offsets(value: Any, transcript: str) -> Any:
    """Deterministically repair only an unambiguous transcript coordinate.

    Models occasionally copy a quote exactly but miscount its UTF-8/character
    offset. A unique verbatim quote has one objectively correct coordinate, so
    correcting that coordinate does not add evidence or alter the model's
    semantic judgment. Ambiguous or non-verbatim quotes remain untouched and
    are rejected by the canonical validator.
    """
    if isinstance(value, list):
        return [_canonicalize_unique_transcript_offsets(item, transcript) for item in value]
    if not isinstance(value, Mapping):
        return value
    normalized = {key: _canonicalize_unique_transcript_offsets(item, transcript) for key, item in value.items()}
    if normalized.get("source") != "transcript" or not isinstance(normalized.get("quote"), str):
        return normalized
    quote = normalized["quote"]
    first = transcript.find(quote)
    if first >= 0 and transcript.find(quote, first + 1) < 0:
        normalized["start_char"], normalized["end_char"] = first, first + len(quote)
    return normalized


def _canonicalize_deterministic_fields(value: Any, transcript: str) -> Any:
    """Apply deterministic output fields after provider output, before validation.

    ``overall_score`` is a published weighted function of the five dimension
    scores, not a model judgment. Calculating it here removes arithmetic drift
    while leaving all interpretive dimensions subject to validation.
    """
    normalized = _canonicalize_unique_transcript_offsets(value, transcript)
    if not isinstance(normalized, Mapping):
        return normalized
    result = dict(normalized)
    dimensions = result.get("dimensions")
    if isinstance(dimensions, Mapping):
        try:
            result["overall_score"] = calculate_overall(dimensions)
        except (KeyError, TypeError, ValueError, ArithmeticError):
            pass
    return result


class OpenAIEvaluator:
    provider_name = "openai"

    def __init__(self, provider: LLMProvider, config: EvaluatorConfig | None = None) -> None:
        self._provider = provider
        self._config = config or EvaluatorConfig()

    def evaluate(self, input_: EvaluationInput) -> EvaluationRun:
        system_prompt = load_system_prompt()
        start = perf_counter()
        try:
            response = self._provider.respond(model=self._config.model, reasoning_effort=self._config.reasoning_effort,
                system_prompt=system_prompt, user_prompt=build_user_prompt(input_), schema=json_schema(),
                max_output_tokens=self._config.max_output_tokens)
        except EvaluationProviderError:
            raise
        except Exception as exc:
            raise EvaluationProviderError("evaluation provider request failed") from exc
        latency_ms = max(0, round((perf_counter() - start) * 1000))
        try:
            raw = json.loads(response.output_text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise EvaluationProviderError("evaluation provider returned invalid JSON") from exc
        if not isinstance(raw, Mapping):
            raise EvaluationProviderError("evaluation provider returned a non-object JSON value")
        try:
            evaluation = validate_evaluation(_canonicalize_deterministic_fields(raw, input_.transcript), input_)
        except EvaluationValidationError as exc:
            raise EvaluationProviderError("evaluation provider returned an invalid evaluation") from exc
        return EvaluationRun(evaluation=evaluation, provider=self.provider_name, model=self._config.model,
            schema_version=SCHEMA_VERSION, evaluation_version=EVALUATION_VERSION, rubric_version=RUBRIC_VERSION,
            prompt_version=PROMPT_VERSION, prompt_sha256=sha256(system_prompt.encode("utf-8")).hexdigest(),
            usage=LLMUsage(response.input_tokens, response.output_tokens, latency_ms, response.request_id))


class GeminiEvaluator(OpenAIEvaluator):
    provider_name = "gemini"


def build_evaluator(settings: EvaluatorSettings, provider: LLMProvider | None = None) -> OpenAIEvaluator:
    """Construct the selected evaluator from application settings.

    ``provider`` is injectable for tests and non-production composition.  The
    factory deliberately accepts a structural settings protocol so it consumes
    ``app.core.Settings`` without importing application composition or routes.
    """
    provider_name = settings.llm_provider.casefold()
    if provider_name not in {"openai", "gemini"}:
        raise EvaluationConfigurationError(f"unsupported evaluator provider {settings.llm_provider!r}")
    model = settings.evaluator_model if provider_name == "openai" else settings.gemini_evaluator_model
    config = EvaluatorConfig(
        model=model,
        reasoning_effort=settings.evaluator_reasoning_effort,
    )
    if provider is None:
        if provider_name == "openai":
            if not settings.openai_api_key:
                raise EvaluationConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
            provider = OpenAIResponsesTransport(settings.openai_api_key)
        else:
            if not settings.gemini_api_key:
                raise EvaluationConfigurationError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
            provider = GeminiGenerateContentTransport(settings.gemini_api_key)
    evaluator_type = OpenAIEvaluator if provider_name == "openai" else GeminiEvaluator
    return evaluator_type(provider, config)


class OpenAIResponsesTransport:
    """Lazy OpenAI Responses API adapter. Construction and tests make no network call."""
    def __init__(self, api_key: str, *, timeout_seconds: float | None = None,
                 max_retries: int | None = None) -> None:
        if not api_key:
            raise ValueError("OpenAI API key must not be blank")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("OpenAI timeout must be positive")
        if max_retries is not None and max_retries < 0:
            raise ValueError("OpenAI max retries must be non-negative")
        self._api_key, self._client = api_key, None
        self._timeout_seconds, self._max_retries = timeout_seconds, max_retries

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise EvaluationProviderError("OpenAI SDK is not installed") from exc
            kwargs = {"api_key": self._api_key}
            if self._timeout_seconds is not None:
                kwargs["timeout"] = self._timeout_seconds
            if self._max_retries is not None:
                kwargs["max_retries"] = self._max_retries
            self._client = OpenAI(**kwargs)
        return self._client

    def respond(self, *, model: str, reasoning_effort: str, system_prompt: str, user_prompt: str, schema: Mapping[str, Any], max_output_tokens: int) -> LLMResponse:
        response = self._get_client().responses.create(model=model, instructions=system_prompt, input=user_prompt,
            reasoning={"effort": reasoning_effort}, text={"format": {"type": "json_schema", "name": "oratry_evaluation", "strict": True, "schema": dict(schema)}},
            max_output_tokens=max_output_tokens)
        usage = getattr(response, "usage", None)
        return LLMResponse(getattr(response, "output_text", ""), getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None), getattr(response, "_request_id", None))


def _gemini_schema(value: Any) -> Any:
    """Translate only portable JSON Schema features used by Oratry's contract.

    Gemini documents a JSON-Schema subset. ``const`` and the draft declaration
    are not part of that subset; an equivalent single-value enum is portable.
    The application still validates every response against the canonical schema.
    """
    if isinstance(value, list):
        return [_gemini_schema(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key == "$schema":
            continue
        if key == "const":
            result["enum"] = [item]
        else:
            result[key] = _gemini_schema(item)
    return result


class GeminiGenerateContentTransport:
    """Gemini REST adapter with native JSON Schema output and no SDK dependency."""

    def __init__(self, api_key: str, *, timeout_seconds: float = 60.0, opener=urlopen) -> None:
        if not api_key:
            raise ValueError("Gemini API key must not be blank")
        if timeout_seconds <= 0:
            raise ValueError("Gemini timeout must be positive")
        self._api_key, self._timeout_seconds, self._opener = api_key, timeout_seconds, opener

    def respond(self, *, model: str, reasoning_effort: str, system_prompt: str,
                user_prompt: str, schema: Mapping[str, Any], max_output_tokens: int) -> LLMResponse:
        del reasoning_effort  # Gemini Flash-Lite selection is configuration-owned; evaluation does not require thinking tokens.
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": _gemini_schema(schema),
                "maxOutputTokens": max_output_tokens,
            },
        }
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self._api_key}",
            data=encoded, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                request_id = response.headers.get("x-request-id")
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise EvaluationProviderError("Gemini evaluator request failed") from exc
        try:
            parts = payload["candidates"][0]["content"]["parts"]
            output = "".join(str(part["text"]) for part in parts if "text" in part)
            usage = payload.get("usageMetadata", {})
            return LLMResponse(output, usage.get("promptTokenCount"), usage.get("candidatesTokenCount"), request_id)
        except (IndexError, KeyError, TypeError) as exc:
            raise EvaluationProviderError("Gemini evaluator returned no usable content") from exc
