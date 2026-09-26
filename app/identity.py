"""OIDC identity-provider boundary for browser sign-in.

Only verified provider claims enter Oratry. OAuth browser state is signed and
short-lived; the browser receives a separate one-time handoff code, never an
Oratry access token in a redirect URL.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import secrets
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import jwt


class IdentityProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExternalProfile:
    provider: str
    subject: str
    email: str


class GoogleIdentityProvider:
    authorization_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    jwks_url = "https://www.googleapis.com/oauth2/v3/certs"

    def __init__(self, *, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.client_id, self.client_secret, self.redirect_uri = client_id, client_secret, redirect_uri
        self._jwks = jwt.PyJWKClient(self.jwks_url, cache_keys=True)

    def authorization_url(self, *, state: str, code_challenge: str) -> str:
        return f"{self.authorization_endpoint}?{urlencode({
            'client_id': self.client_id, 'redirect_uri': self.redirect_uri,
            'response_type': 'code', 'scope': 'openid email profile', 'state': state,
            'code_challenge': code_challenge, 'code_challenge_method': 'S256',
            'prompt': 'select_account',
        })}"

    def exchange(self, *, code: str, code_verifier: str) -> ExternalProfile:
        body = urlencode({
            "code": code, "client_id": self.client_id, "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri, "grant_type": "authorization_code", "code_verifier": code_verifier,
        }).encode("utf-8")
        request = Request(self.token_endpoint, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read())
            id_token = payload.get("id_token")
            if not isinstance(id_token, str):
                raise ValueError("missing id token")
            key = self._jwks.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(id_token, key.key, algorithms=["RS256"], audience=self.client_id,
                                issuer=["https://accounts.google.com", "accounts.google.com"])
            subject, email = claims.get("sub"), claims.get("email")
            if not isinstance(subject, str) or not isinstance(email, str) or claims.get("email_verified") is not True:
                raise ValueError("Google account email is not verified")
            return ExternalProfile("google", subject, email.casefold())
        except Exception as exc:
            raise IdentityProviderError("Google sign-in could not be verified") from exc


def new_browser_state(*, accepted_terms: bool) -> tuple[str, str, str]:
    state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
    challenge = sha256(verifier.encode("ascii")).digest()
    import base64
    return state, verifier, base64.urlsafe_b64encode(challenge).rstrip(b"=").decode("ascii")


def state_cookie(*, state: str, verifier: str, accepted_terms: bool, secret: str, expires_seconds: int) -> str:
    from datetime import datetime, timedelta, timezone
    return jwt.encode({"state": state, "verifier": verifier, "terms": accepted_terms,
                       "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)}, secret, algorithm="HS256")


def read_state_cookie(value: str | None, *, state: str, secret: str) -> tuple[str, bool] | None:
    if not value:
        return None
    try:
        payload = jwt.decode(value, secret, algorithms=["HS256"])
        expected, verifier, terms = payload.get("state"), payload.get("verifier"), payload.get("terms")
        if not isinstance(expected, str) or not isinstance(verifier, str) or not isinstance(terms, bool):
            return None
        if not hmac.compare_digest(expected, state):
            return None
        return verifier, terms
    except jwt.PyJWTError:
        return None


def digest_code(code: str) -> str:
    return sha256(code.encode("utf-8")).hexdigest()


def new_handoff_code() -> str:
    return secrets.token_urlsafe(32)
