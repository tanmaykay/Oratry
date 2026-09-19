"""Email delivery boundary for account-security messages.

The application never persists or logs a plaintext activation token.  The
development implementation keeps messages in process memory solely to make a
local preview testable; it is intentionally unavailable outside local/test.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmailDeliveryError(RuntimeError):
    """Raised when configured email delivery cannot safely accept a message."""


class EmailProvider(Protocol):
    def send_signup_activation(self, *, recipient: str, activation_url: str) -> None:
        """Deliver one activation URL without retaining it in application data."""


@dataclass(frozen=True)
class DevelopmentOutboxMessage:
    recipient: str
    activation_url: str


class DevelopmentOutboxEmailProvider:
    """In-memory local-only outbox; never write activation URLs to logs or disk."""

    def __init__(self) -> None:
        self.messages: list[DevelopmentOutboxMessage] = []

    def send_signup_activation(self, *, recipient: str, activation_url: str) -> None:
        self.messages.append(DevelopmentOutboxMessage(recipient=recipient, activation_url=activation_url))

    def latest_for(self, recipient: str) -> DevelopmentOutboxMessage | None:
        normalized = recipient.casefold()
        return next((message for message in reversed(self.messages) if message.recipient.casefold() == normalized), None)


class DisabledEmailProvider:
    """An explicit fail-closed provider for unconfigured deployments."""

    def send_signup_activation(self, *, recipient: str, activation_url: str) -> None:
        raise EmailDeliveryError("Transactional email delivery is not configured")


class ResendEmailProvider:
    """Resend HTTP adapter; no vendor concerns escape the EmailProvider port."""

    endpoint = "https://api.resend.com/emails"

    def __init__(self, *, api_key: str, from_address: str,
                 transport: Callable[[Request, float], None] | None = None) -> None:
        if not api_key or not from_address:
            raise ValueError("Resend requires an API key and sender address")
        self.api_key = api_key
        self.from_address = from_address
        self._transport = transport or self._send

    def send_signup_activation(self, *, recipient: str, activation_url: str) -> None:
        body = json.dumps({
            "from": self.from_address,
            "to": [recipient],
            "subject": "Activate your Oratry account",
            "html": (
                "<p>Welcome to Oratry.</p>"
                f'<p><a href="{activation_url}">Activate your account</a></p>'
                "<p>This link expires in 24 hours.</p>"
            ),
        }).encode("utf-8")
        request = Request(self.endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        try:
            self._transport(request, 10.0)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise EmailDeliveryError("Resend could not accept the activation email") from exc

    @staticmethod
    def _send(request: Request, timeout: float) -> None:
        with urlopen(request, timeout=timeout) as response:
            if not 200 <= response.status < 300:
                raise EmailDeliveryError("Resend rejected the activation email")
