# Oratry web client design

The Next.js/React/TypeScript client currently supplies a clickable mock preview of the V1 product flow. It is not yet authenticated or connected to the FastAPI API; implementation reality is maintained in `project/CURRENT_STATE.md`.

## Design and behavior

- The design system is intentionally small: shared buttons, cards, labels, scores, empty states, responsive application shell, and one CSS token set.
- Objective recording/transcript facts are in a distinct Results section from AI interpretation and the coaching recommendation.
- The speaking view removes product chrome and leaves only the prompt, timer, recording control, and exit affordance.
- Keyboard-native controls, visible semantic labels, and responsive desktop/mobile styles are used throughout.

## Backend dependencies

`features/shared/api/client.ts` is intended to be the sole browser API boundary. It currently supplies mock fallbacks and does not match the authenticated backend contract; replace it as the endpoints are implemented:

- Auth/session: `/auth/sign-up`, `/auth/sign-in`, `/me`.
- Baseline/current assignment/home: `/baseline`, `/assignments/current`, `/home`.
- Challenge and recording lifecycle: assignment attempt creation, signed upload, upload completion, attempt status/result/comparison.
- Progress skill trends and user-managed vocabulary CRUD.

The browser still needs a dedicated recorder/upload adapter wired to the signed-upload contract before production recording is enabled; no provider SDK or scoring logic belongs in the UI.
