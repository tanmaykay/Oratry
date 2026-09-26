# Oratry V1 API Contracts

## Contract status

This is the implemented V1 API contract unless a route is explicitly labelled future. Consult `project/CURRENT_STATE.md` for live-provider verification status. Route status is maintained by the Architect/Orchestrator, not by specialist workstreams.

## Conventions

All endpoints are versioned under `/v1`, require an authenticated user session except signup/signin, and return JSON using `camelCase`. Timestamps are ISO-8601 UTC strings; IDs are opaque UUIDs. The API returns RFC 7807-style error objects with `code`, `message`, and optional `fieldErrors`. Authorization failure must not reveal whether another user's resource exists.

Target writes accept an `Idempotency-Key` header and return the original successful result for repeated keys on the same authenticated route. Target page lists use cursor pagination where applicable.

## Auth and profile

| Method / path | Request | Success response |
| --- | --- | --- |
| `POST /v1/auth/sign-up` | email, password, acceptedTerms | unverified user and activation-delivery acknowledgement |
| `POST /v1/auth/sign-in` | email, password | user and session |
| `GET /v1/auth/providers` | none | enabled public sign-in methods |
| `GET /v1/auth/google/start` | optional acceptedTerms query | browser redirect to Google with PKCE/state |
| `GET /v1/auth/google/callback` | provider callback | browser redirect to web app with one-time handoff code |
| `POST /v1/auth/google/complete` | one-time handoff code | user and session |
| `POST /v1/auth/sign-out` | none | `204` |
| `GET /v1/me` | none | profile, onboarding state, current assignment summary |
| `PATCH /v1/me` | supported profile/preferences fields | updated profile |

Authentication implementation (hosted identity provider or first-party credentials) is deliberately replaceable; API behavior is the contract.

Google callback redirects never contain an Oratry session token. The opaque
handoff code expires in five minutes by default and may be consumed once.

## Baseline, home, and curriculum

| Method / path | Purpose |
| --- | --- |
| `POST /v1/baseline/start` | Creates or returns the active baseline assessment and initial assignments. |
| `GET /v1/baseline` | Returns baseline status and required assignment summaries. |
| `GET /v1/home` | Returns the active assignment, in-progress attempt, coaching focus, and concise recent progress. |
| `GET /v1/assignments/current` | Returns the next practice assignment and immutable challenge version. |
| `GET /v1/challenges/{challengeId}` | Returns a challenge only when assigned to the caller. |

`ChallengeAssignmentResponse` includes `assignmentId`, `status`, `reason`, and `challenge`: `{ id, version, prompt, preparationGuidance, targetSkills, targetVocabulary, targetDurationSeconds, difficulty }`. `targetVocabulary` is versioned challenge-owned lexical context used for deterministic coverage, not a requirement to force unfamiliar words into a response. The response does not include hidden evaluation instructions or LLM prompts.

## Recording and analysis

| Method / path | Request | Success response |
| --- | --- | --- |
| `POST /v1/assignments/{assignmentId}/attempts` | `contentType`, SHA-256 `checksumSha256`, optional `retryOfAttemptId` | attempt in `uploading` state and an `upload` instruction |
| `POST /v1/attempts/{attemptId}/upload-complete` | `objectKey`, `durationSeconds`, `contentType`, `byteSize` | attempt in `queued` state, `202` |
| `GET /v1/attempts/{attemptId}` | none | attempt summary, lifecycle status, challenge snapshot |
| `GET /v1/attempts/{attemptId}/result` | none | completed analysis result; `409 analysis_not_complete` otherwise |
| `GET /v1/attempts/{attemptId}/recording-playback` | none | owner-authorized, short-lived private `GET` URL while raw audio remains retained |
| `GET /v1/attempts/{attemptId}/analysis-status` | none | status, stage, retry-safe user message, `updatedAt` |
| `GET /v1/attempts/{attemptId}/comparison` | none | original/retry summaries when both are complete |

`upload` is `{ method, url, headers, objectKey, expiresAt }` for a direct private object-store upload. The browser computes `checksumSha256` over the finalized blob before requesting the instruction, then uses every returned upload header verbatim. The browser may only upload the key returned by this call. The server verifies content type, byte size, checksum observed from object storage, and caller-owned key before sealing the attempt. Completion atomically persists a durable, idempotent analysis-job delivery. Recording metadata stores a configurable retention deadline and deletion state (`not_scheduled`, `scheduled`, `deleting`, `deleted`, or `delete_failed`); recording bytes never receive permanent public URLs. Playback signs a private object-store `GET` only after owner authorization; it returns `410 recording_unavailable` after deletion begins or the retention deadline passes, even if a background deletion retry has not run yet.

`AttemptResultResponse` separates facts from interpretation:

```json
{
  "attemptId": "uuid",
  "analysisVersion": 1,
  "transcript": { "text": "...", "segments": [{ "startMs": 0, "endMs": 820, "text": "..." }] },
  "objectiveMetrics": [{ "name": "wordsPerMinute", "value": 132, "unit": "wpm", "source": "transcript", "calculationVersion": "1" }],
  "scorecard": { "scale": "0-100", "structure": 72, "clarity": 70, "fluency": 64, "language": 68, "delivery": 66, "overall": 68, "scorerVersion": "1" },
  "evaluation": { "dimensionObservations": [], "evidence": [], "disclaimer": "AI interpretation based on your recording and transcript." },
  "coachingRecommendation": { "focusSkill": "fluency", "observation": "...", "action": "...", "successCriterion": "..." }
}
```

The web app polls `analysis-status` with bounded backoff while the attempt is queued/analyzing. WebSockets are not needed for V1.

## Progress and vocabulary

| Method / path | Purpose |
| --- | --- |
| `GET /v1/progress` | Returns score/skill trend series, recent evidence, and comparison-ready attempt summaries. |
| `GET /v1/progress/skills` | Returns current skill-state projections and confidence. |
| `GET /v1/vocabulary` | Lists caller-owned vocabulary items. |
| `POST /v1/vocabulary` | Creates a user-entered word/phrase item. |
| `PATCH /v1/vocabulary/{itemId}` | Updates saved item or practice status. |
| `DELETE /v1/vocabulary/{itemId}` | Deletes caller-owned item. |

Progress responses label calculated scores, objective measurements, and AI observations separately. Trend data includes analysis/scorer versions so clients can label incomparable historical changes if versions later diverge.

## Internal worker contract

Only workers can consume `attempt.analysis.requested` jobs. Minimum payload:

```json
{ "eventId": "uuid", "attemptId": "uuid", "analysisVersion": 1, "requestedAt": "2026-09-12T00:00:00Z" }
```

Consumers acknowledge only after recording an idempotent stage transition. The queue may redeliver messages in any order; the application service checks legal state and already-completed stage outputs. No provider webhook is required in V1; if a selected provider is asynchronous, its adapter owns polling and normalizes the result before the next pipeline stage.

Each analysis run records provider, operation, input/output units, estimated cost in USD, and latency in milliseconds. This operational data is not learner-facing scoring input.
