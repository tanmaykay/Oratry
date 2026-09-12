# Oratry V1 web app

The web client is a new Next.js/React/TypeScript application. It supplies the complete V1 product flow: landing and signup, onboarding/baseline, Home, challenge selection and briefing, preparation, minimal recording, analysis status, results, single-focus feedback, retry/comparison, Progress, Vocabulary, and Profile.

## Design and behavior

- The design system is intentionally small: shared buttons, cards, labels, scores, empty states, responsive application shell, and one CSS token set.
- Objective recording/transcript facts are in a distinct Results section from AI interpretation and the coaching recommendation.
- The speaking view removes product chrome and leaves only the prompt, timer, recording control, and exit affordance.
- Keyboard-native controls, visible semantic labels, and responsive desktop/mobile styles are used throughout.

## Backend dependencies

`features/shared/api/client.ts` is the sole API boundary. It is shaped around the documented `/v1` contracts and temporarily supplies fallback display data when the API is unavailable. Replace fallbacks as the endpoints are implemented:

- Auth/session: `/auth/sign-up`, `/auth/sign-in`, `/me`.
- Baseline/current assignment/home: `/baseline`, `/assignments/current`, `/home`.
- Challenge and recording lifecycle: assignment attempt creation, signed upload, upload completion, attempt status/result/comparison.
- Progress skill trends and user-managed vocabulary CRUD.

The browser still needs a dedicated recorder/upload adapter wired to the signed-upload contract before production recording is enabled; no provider SDK or scoring logic belongs in the UI.
