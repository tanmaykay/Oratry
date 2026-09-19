import json

import pytest

from app.email import EmailDeliveryError, ResendEmailProvider


def test_resend_adapter_sends_expected_activation_message_without_live_network():
    captured = {}

    def transport(request, timeout):
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout

    provider = ResendEmailProvider(api_key="re_test", from_address="Oratry <accounts@example.test>", transport=transport)
    provider.send_signup_activation(recipient="learner@example.test", activation_url="https://app.example.test/activate?token=secret")
    assert captured["headers"]["Authorization"] == "Bearer re_test"
    assert captured["body"]["to"] == ["learner@example.test"]
    assert "https://app.example.test/activate?token=secret" in captured["body"]["html"]
    assert captured["timeout"] == 10.0


def test_resend_adapter_normalizes_transport_failure():
    def transport(_request, _timeout):
        raise OSError("offline")

    provider = ResendEmailProvider(api_key="re_test", from_address="accounts@example.test", transport=transport)
    with pytest.raises(EmailDeliveryError):
        provider.send_signup_activation(recipient="learner@example.test", activation_url="https://app.example.test/activate?token=secret")
