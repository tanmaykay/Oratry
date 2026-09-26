# Analysis worker operations

The analysis worker is separate from FastAPI. It leases one durable
`analysis_jobs` delivery at a time and needs the same database, R2, Deepgram,
and configured evaluator configuration as the API.

Run one job for local diagnosis:

```powershell
.\.venv\Scripts\python.exe -m app.worker --once
```

Run continuously under a process supervisor:

```powershell
.\.venv\Scripts\python.exe -m app.worker --worker-id analysis-local-1
```

The process accepts Ctrl+C/SIGTERM. It stops claiming new jobs and lets an
already-started provider call finish. Check database reachability without
calling providers:

```powershell
.\.venv\Scripts\python.exe -m app.worker --health
```

## Delivery and recovery

Every claim has a unique owner token. Completion, failure, and lease renewal
are conditional on that token and an unexpired lease. A stale worker therefore
cannot overwrite a later worker's state. The worker renews before and after
external storage/STT/evaluator boundaries. Deepgram prerecorded requests are
bounded at 60 seconds; `ANALYSIS_JOB_LEASE_SECONDS` has a 75-second minimum.
Deepgram requests explicitly enable `filler_words=true`, because the provider
otherwise strips `um` and `uh` from a conventional transcript. Timestamped
internal word gaps provide the portable V1 pause metrics for browser-recorded
WebM; they are labelled separately from acoustic silence analysis.
The configured evaluator uses `ANALYSIS_LLM_TIMEOUT_SECONDS`, which must be below the lease. OpenAI SDK retries are disabled for worker calls; Gemini uses a single bounded HTTP request. Durable job retry is the only retry authority.

Transient STT transport failures and evaluator transport failures retry with
bounded exponential delay. Invalid STT content, invalid strict evaluator
output, missing recordings, and authorization failures are terminal. Operator
requeue is deliberately an internal, authorized service operation; no public
API route exposes it.

For the current local V1 configuration:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_EVALUATOR_MODEL=gemini-3.5-flash-lite
```

Gemini output is constrained to the canonical JSON Schema and then validated
for exact transcript/metric evidence. A unique verbatim quote's offsets and
the published weighted overall score are derived deterministically; ambiguous
or unsupported evidence is rejected.

Set these deployment configuration values when you want cost estimates:

```dotenv
ANALYSIS_JOB_LEASE_SECONDS=120
ANALYSIS_LLM_TIMEOUT_SECONDS=60
ANALYSIS_WORKER_POLL_SECONDS=2
ANALYSIS_COST_VERSION=provider-price-YYYY-MM
STT_COST_USD_PER_AUDIO_MINUTE=
LLM_INPUT_COST_USD_PER_MILLION_TOKENS=
LLM_OUTPUT_COST_USD_PER_MILLION_TOKENS=
```

Blank price settings retain actual duration/tokens/latency/request IDs but
record `estimatedCostUsd: null`; no provider price is hard-coded in Oratry.
Outside local/test environments, worker startup rejects blank rates or the
`unconfigured` cost version so operational accounting cannot be silently lost.

If an evaluator transport failure is retried, the worker reuses its persisted,
immutable transcript, deterministic metrics, and STT usage evidence. It does
not call STT or alter that evidence again.
