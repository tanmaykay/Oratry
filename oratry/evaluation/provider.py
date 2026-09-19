"""OpenAI adapter for the canonical, validated Oratry evaluation contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Protocol

from schemas.evaluation import EVALUATION_VERSION, PROMPT_VERSION, RUBRIC_VERSION, SCHEMA_VERSION, EvaluationInput, EvaluationValidationError, json_schema, validate_evaluation

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
            evaluation = validate_evaluation(raw, input_)
        except EvaluationValidationError as exc:
            raise EvaluationProviderError("evaluation provider returned an invalid evaluation") from exc
        return EvaluationRun(evaluation=evaluation, provider=self.provider_name, model=self._config.model,
            schema_version=SCHEMA_VERSION, evaluation_version=EVALUATION_VERSION, rubric_version=RUBRIC_VERSION,
            prompt_version=PROMPT_VERSION, prompt_sha256=sha256(system_prompt.encode("utf-8")).hexdigest(),
            usage=LLMUsage(response.input_tokens, response.output_tokens, latency_ms, response.request_id))


def build_evaluator(settings: EvaluatorSettings, provider: LLMProvider | None = None) -> OpenAIEvaluator:
    """Construct the selected evaluator from application settings.

    ``provider`` is injectable for tests and non-production composition.  The
    factory deliberately accepts a structural settings protocol so it consumes
    ``app.core.Settings`` without importing application composition or routes.
    """
    if settings.llm_provider.casefold() != "openai":
        raise EvaluationConfigurationError(
            f"unsupported evaluator provider {settings.llm_provider!r}; expected 'openai'"
        )
    config = EvaluatorConfig(
        model=settings.evaluator_model,
        reasoning_effort=settings.evaluator_reasoning_effort,
    )
    if provider is None:
        if not settings.openai_api_key:
            raise EvaluationConfigurationError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        provider = OpenAIResponsesTransport(settings.openai_api_key)
    return OpenAIEvaluator(provider, config)


class OpenAIResponsesTransport:
    """Lazy OpenAI Responses API adapter. Construction and tests make no network call."""
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OpenAI API key must not be blank")
        self._api_key, self._client = api_key, None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:  # pragma: no cover
                raise EvaluationProviderError("OpenAI SDK is not installed") from exc
            self._client = OpenAI(api_key=self._api_key)
        return self._client

    def respond(self, *, model: str, reasoning_effort: str, system_prompt: str, user_prompt: str, schema: Mapping[str, Any], max_output_tokens: int) -> LLMResponse:
        response = self._get_client().responses.create(model=model, instructions=system_prompt, input=user_prompt,
            reasoning={"effort": reasoning_effort}, text={"format": {"type": "json_schema", "name": "oratry_evaluation", "strict": True, "schema": dict(schema)}},
            max_output_tokens=max_output_tokens)
        usage = getattr(response, "usage", None)
        return LLMResponse(getattr(response, "output_text", ""), getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None), getattr(response, "_request_id", None))
