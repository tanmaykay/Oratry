# ADR 0005: Google OIDC uses PKCE and a one-time browser handoff

## Status

Accepted — implementation is configuration-gated.

## Decision

Oratry supports Google sign-in through the OAuth authorization-code flow with
PKCE. The API owns the OAuth callback and verifies the Google ID token’s
signature, issuer, audience, subject, and verified-email claim. It stores the
provider subject in `external_identities`, not an access token.

The callback redirects to the web app with a short-lived, single-use opaque
handoff code. The web app exchanges that code through the API for the existing
Oratry bearer session. The redirect never contains an Oratry access token.

OAuth state, PKCE verifier, and first-account terms acknowledgement are kept in
a signed, HTTP-only, SameSite=Lax API cookie for ten minutes. A new Google user
must acknowledge terms in the UI; an existing linked identity may sign in.

## Consequences

- Google client ID, secret, callback URI, API origin, and web origin are
  deployment configuration. No Google credentials are committed.
- The design works when API and web use distinct HTTPS origins, as long as the
  browser begins the redirect at the API origin.
- Future identity providers can implement the same verified-profile boundary
  and reuse the external identity and handoff-code records.
