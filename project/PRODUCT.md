# Oratry product definition

Oratry is a web-first personal training system for clear thinking and speaking. Its V1 outcome is a user completing a baseline challenge, receiving useful evidence-backed coaching, retrying the same challenge, and seeing an honest comparison and progress update.

## Product thesis

Oratry trains the cognitive process around speaking, not merely vocal delivery:

`information -> understanding -> thinking -> formulation -> structure -> word retrieval -> speaking -> delivery`

Its promise is **Think better. Speak better.** AI assists reflection and coaching after the learner has done the thinking; it does not formulate the learner's answer for them. The durable product value is a longitudinal skill profile and a progressively adapted curriculum, not a generic transcript, a collection of speech metrics, or a chat interface.

V1 is designed first for ambitious English-speaking students and early-career professionals who want to explain ideas more clearly, handle interviews and spontaneous questions better, and turn practice into visible improvement.

The learning loop is:

`Think -> Speak -> Analyze -> Correct -> Retry -> Progress`

V1 must distinguish measured facts (for example duration, WPM, filler count, pause estimates, repetitions, and target-word occurrence) from model-assisted interpretation (argument structure, clarity, coherence, vocabulary appropriateness, and coaching). A user receives exactly one practical primary insight per completed attempt.

Raw recordings are sensitive content. They require private storage, intentional retention/deletion behavior, and server-side authorization.

## V1 experience constraints

- The challenge is the central product experience: prepare independently, speak, receive one primary coaching insight, retry, then see an honest comparison.
- Home prioritizes today's challenge and the learner's current focus over a broad dashboard.
- Vocabulary is active retrieval practice, not a generic word list. Definitions and examples may help preparation, but progress is earned through deliberate and eventually natural spoken use.
- The challenge catalog is curated and versioned. New modes may be planned in advance, but become selectable only after their preparation experience, rubric, and evaluation behavior are validated; see `docs/challenge-catalog.md`.
- V1 does not make psychological claims from audio, provide a nervousness score, analyze sentiment or body language, build a research browser, or use AI to think on the learner's behalf.
- Scores are secondary to actionable coaching. Objective measures, model-derived observations, and coaching judgment must remain distinguishable.
