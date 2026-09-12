# AI evaluation design

## Purpose and decision

This package tests whether a prompt-based evaluator can produce trustworthy, constrained observations before any fine-tuning. It is not a production claim that an LLM score is ground truth. The evaluation stage receives `challenge`, `prompt`, `target_skill`, `transcript`, `speech_metrics`, `target_vocabulary`, `previous_performance`, and `user_skill_profile`; only the current transcript and metrics may substantiate current-attempt evidence.

The system separates three layers:

1. Objective pipeline facts: timestamped transcript and versioned metrics.
2. LLM interpretation: five bounded dimension judgments with traceable evidence.
3. Deterministic product scoring/coaching: published weights calculate the overall score; one validated primary weakness determines the retry focus.

This follows the architecture's provider boundary: the LLM adapter returns canonical JSON, validates it with `schemas.evaluation.validate_evaluation`, persists prompt/model/rubric versions, and rejects—not repairs—invalid output. Coaching consumes a completed evaluation and does not make a second LLM call.

## Contract and controls

`schemas/evaluation.py` exposes schema version `1.0.0`, a JSON Schema for structured-output provider APIs, exact evidence validation, and deterministic scoring. Provider configuration should use structured JSON/schema mode, temperature `0`, a pinned model snapshot, fixed system prompt, and a fixed maximum output token limit. Record provider, model identifier, prompt version, rubric version, metric calculation version, schema version, and scorer version on every `AnalysisRun`.

Validation should run after every provider response. On malformed JSON, unsupported version, unsupported metric/quote, bad offsets, wrong weighted total, or extra keys: save a redacted validation failure, retry at the evaluation stage under its idempotency key, then surface the normal safe analysis failure if retries are exhausted. Never silently substitute a result from a different prompt/model revision.

## Safety and fairness policy

- Observations cite only exact input evidence; interpretations are explicitly separated.
- Do not infer confidence, anxiety, effort, intelligence, personality, emotion, diagnosis, or motivation.
- Accent and native-language status are not scoring criteria. Delivery is limited to measurable supplied pacing/timing evidence.
- Vocabulary complexity and response length are not rewarded alone. Accuracy, relevance, and effective communication are.
- Missing metrics remain unavailable. The evaluator must lower confidence or list a limitation, not fabricate a zero.
- The output contains one primary weakness and one action, not an exhaustive critique.

## Trustworthiness experiment

The test suite provides 11 contrastive fixtures. Run `python -m unittest discover -s tests -v`. For a provider trial, submit each fixture repeatedly (for example 10 runs) with the production controls above, retain raw output privately, and measure:

- schema-valid response rate and evidence-validation pass rate (target: 100% after retry);
- deterministic overall-score correctness (target: 100%);
- rubric agreement with two independent human raters per dimension (predefine an acceptable weighted MAE and inter-rater comparison before launch);
- rank ordering for deliberately paired cases (structured > rambling; simple-clear > ornate-disorganized; on-topic > off-topic);
- safety errors: invented evidence, accent penalty, psychological claim, verbosity reward, or more than one primary weakness (target: 0);
- repeatability: score range and primary-weakness agreement across repeated identical calls.

Blind raters to model output while creating labels. Inspect disagreements by dimension and input availability, then revise rubric/prompt versions and rerun the frozen suite. Do not fine-tune until the prompt approach meets predeclared reliability, safety, and stability thresholds on held-out consented attempts as well as these synthetic fixtures.

## Integration boundary

The API never exposes hidden prompts. The worker supplies canonical input to the evaluation adapter, validates the response, stores it as interpretation, then creates a versioned scorecard. UI displays objective metrics separately from AI observations and labels the latter as AI interpretation. Historical evaluations and scorecards are immutable; any prompt/rubric/scorer change creates a new analysis version.
