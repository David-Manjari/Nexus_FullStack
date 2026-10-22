import pytest
import requests

from backend.integrations import daraja_b2c


def _sandbox_config(monkeypatch):
    settings = {
        "DARAJA_B2C_ENABLED": "true",
        "DARAJA_CONSUMER_KEY": "sandbox-key",
        "DARAJA_CONSUMER_SECRET": "sandbox-secret",
        "DARAJA_INITIATOR_NAME": "sandbox-initiator",
        "DARAJA_SECURITY_CREDENTIAL": "encrypted-sandbox-credential",
        "DARAJA_SHORTCODE": "600000",
        "DARAJA_CALLBACK_BASE_URL": "https://example.test",
        "DARAJA_CALLBACK_TOKEN": "a" * 40,
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    return daraja_b2c.DarajaConfig.from_env()


def test_sandbox_is_disabled_unless_explicitly_enabled(monkeypatch):
    monkeypatch.delenv("DARAJA_B2C_ENABLED", raising=False)

    with pytest.raises(daraja_b2c.DarajaConfigurationError, match="disabled"):
        daraja_b2c.DarajaConfig.from_env()


def test_sandbox_config_builds_https_callback_urls(monkeypatch):
    config = _sandbox_config(monkeypatch)

    assert config.result_url == (
        "https://example.test/api/daraja/b2c/result/" + "a" * 40
    )
    assert config.timeout_url == (
        "https://example.test/api/daraja/b2c/timeout/" + "a" * 40
    )


def test_sandbox_rejects_non_https_callbacks(monkeypatch):
    _sandbox_config(monkeypatch)
    monkeypatch.setenv("DARAJA_CALLBACK_BASE_URL", "http://example.test")

    with pytest.raises(daraja_b2c.DarajaConfigurationError, match="HTTPS"):
        daraja_b2c.DarajaConfig.from_env()


def test_oauth_token_is_cached_and_uses_sandbox(monkeypatch):
    config = _sandbox_config(monkeypatch)
    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"access_token": "temporary-token", "expires_in": 3600}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(daraja_b2c.requests, "get", fake_get)
    monkeypatch.setattr(daraja_b2c, "_cached_token", None)
    monkeypatch.setattr(daraja_b2c, "_token_expires_at", 0.0)
    monkeypatch.setattr(daraja_b2c, "_cached_credentials", None)

    assert daraja_b2c.get_access_token(config) == "temporary-token"
    assert daraja_b2c.get_access_token(config) == "temporary-token"
    assert len(calls) == 1
    assert calls[0][0] == "https://sandbox.safaricom.co.ke/oauth/v1/generate"
    assert calls[0][1]["auth"] == ("sandbox-key", "sandbox-secret")


def test_b2c_submission_uses_sandbox_payload(monkeypatch):
    config = _sandbox_config(monkeypatch)
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {
                "ResponseCode": "0",
                "ConversationID": "conversation-1",
                "OriginatorConversationID": "originator-1",
                "ResponseDescription": "Accepted",
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(daraja_b2c.requests, "post", fake_post)
    result = daraja_b2c.submit_b2c(
        config,
        "temporary-token",
        amount=125,
        phone_number="254712345678",
        reference="NEX-REFERENCE",
        occasion="Approved test payout",
    )

    assert captured["url"] == (
        "https://sandbox.safaricom.co.ke/mpesa/b2c/v1/paymentrequest"
    )
    assert captured["headers"] == {"Authorization": "Bearer temporary-token"}
    assert captured["json"]["PartyB"] == "254712345678"
    assert captured["json"]["Amount"] == 125
    assert captured["json"]["ResultURL"] == config.result_url
    assert result["conversation_id"] == "conversation-1"
    assert result["originator_conversation_id"] == "originator-1"


def test_b2c_transport_failure_is_not_reported_as_failed_payment(monkeypatch):
    config = _sandbox_config(monkeypatch)

    def fail_post(*args, **kwargs):
        raise requests.Timeout("request timed out")

    monkeypatch.setattr(daraja_b2c.requests, "post", fail_post)

    with pytest.raises(daraja_b2c.DarajaSubmissionUncertain):
        daraja_b2c.submit_b2c(
            config,
            "temporary-token",
            amount=125,
            phone_number="254712345678",
            reference="NEX-REFERENCE",
            occasion="Approved test payout",
        )
