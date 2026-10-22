"""Safaricom Daraja B2C sandbox client."""

import os
import threading
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests

SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"
OAUTH_URL = f"{SANDBOX_BASE_URL}/oauth/v1/generate"
B2C_URL = f"{SANDBOX_BASE_URL}/mpesa/b2c/v1/paymentrequest"
COMMAND_IDS = {"BusinessPayment", "SalaryPayment", "PromotionPayment"}


class DarajaConfigurationError(RuntimeError):
    """The sandbox integration is not configured safely."""


class DarajaRejected(RuntimeError):
    """Daraja explicitly rejected a payout submission."""


class DarajaSubmissionUncertain(RuntimeError):
    """A payout submission may have reached Daraja but was not confirmed."""


@dataclass(frozen=True)
class DarajaConfig:
    consumer_key: str
    consumer_secret: str
    initiator_name: str
    security_credential: str
    shortcode: str
    callback_base_url: str
    callback_token: str
    command_id: str

    @classmethod
    def from_env(cls):
        if os.environ.get("DARAJA_B2C_ENABLED", "").lower() != "true":
            raise DarajaConfigurationError(
                "Daraja B2C sandbox payouts are disabled. Set DARAJA_B2C_ENABLED=true."
            )

        values = {
            "consumer_key": os.environ.get("DARAJA_CONSUMER_KEY", "").strip(),
            "consumer_secret": os.environ.get("DARAJA_CONSUMER_SECRET", "").strip(),
            "initiator_name": os.environ.get("DARAJA_INITIATOR_NAME", "").strip(),
            "security_credential": os.environ.get(
                "DARAJA_SECURITY_CREDENTIAL", ""
            ).strip(),
            "shortcode": os.environ.get("DARAJA_SHORTCODE", "").strip(),
            "callback_base_url": os.environ.get(
                "DARAJA_CALLBACK_BASE_URL", ""
            ).strip().rstrip("/"),
            "callback_token": os.environ.get("DARAJA_CALLBACK_TOKEN", "").strip(),
            "command_id": os.environ.get(
                "DARAJA_B2C_COMMAND_ID", "BusinessPayment"
            ).strip(),
        }
        required = (
            "consumer_key",
            "consumer_secret",
            "initiator_name",
            "security_credential",
            "shortcode",
            "callback_base_url",
            "callback_token",
        )
        missing = [name for name in required if not values[name]]
        if missing:
            raise DarajaConfigurationError(
                "Missing Daraja sandbox settings: " + ", ".join(missing) + "."
            )
        callback_url = urlsplit(values["callback_base_url"])
        if (
            callback_url.scheme != "https"
            or not callback_url.hostname
            or callback_url.username
            or callback_url.password
            or callback_url.query
            or callback_url.fragment
        ):
            raise DarajaConfigurationError(
                "DARAJA_CALLBACK_BASE_URL must use public HTTPS."
            )
        if not values["shortcode"].isdigit():
            raise DarajaConfigurationError("DARAJA_SHORTCODE must contain digits only.")
        if len(values["callback_token"]) < 32:
            raise DarajaConfigurationError(
                "DARAJA_CALLBACK_TOKEN must contain at least 32 characters."
            )
        if values["command_id"] not in COMMAND_IDS:
            raise DarajaConfigurationError(
                "DARAJA_B2C_COMMAND_ID must be BusinessPayment, SalaryPayment, "
                "or PromotionPayment."
            )
        return cls(**values)

    @property
    def result_url(self):
        return (
            f"{self.callback_base_url}/api/daraja/b2c/result/"
            f"{self.callback_token}"
        )

    @property
    def timeout_url(self):
        return (
            f"{self.callback_base_url}/api/daraja/b2c/timeout/"
            f"{self.callback_token}"
        )


_token_lock = threading.Lock()
_cached_token = None
_token_expires_at = 0.0
_cached_credentials = None


def get_access_token(config):
    global _cached_token, _token_expires_at, _cached_credentials
    credentials = (config.consumer_key, config.consumer_secret)
    now = time.monotonic()
    if (
        _cached_token
        and _cached_credentials == credentials
        and now < _token_expires_at
    ):
        return _cached_token

    with _token_lock:
        now = time.monotonic()
        if (
            _cached_token
            and _cached_credentials == credentials
            and now < _token_expires_at
        ):
            return _cached_token
        try:
            response = requests.get(
                OAUTH_URL,
                params={"grant_type": "client_credentials"},
                auth=(config.consumer_key, config.consumer_secret),
                timeout=10,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as error:
            raise DarajaConfigurationError(
                "Could not authenticate with the Daraja sandbox."
            ) from error

        if not isinstance(payload, dict):
            raise DarajaConfigurationError(
                "Daraja sandbox returned an invalid authentication response."
            )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise DarajaConfigurationError(
                "Daraja sandbox did not return an access token."
            )
        try:
            expires_in = max(int(payload.get("expires_in", 3600)), 60)
        except (TypeError, ValueError):
            expires_in = 3600
        _cached_token = token
        _cached_credentials = credentials
        _token_expires_at = time.monotonic() + expires_in - 30
        return token


def submit_b2c(config, access_token, *, amount, phone_number, reference, occasion):
    payload = {
        "InitiatorName": config.initiator_name,
        "SecurityCredential": config.security_credential,
        "CommandID": config.command_id,
        "Amount": int(amount),
        "PartyA": config.shortcode,
        "PartyB": phone_number,
        "Remarks": reference[:100],
        "QueueTimeOutURL": config.timeout_url,
        "ResultURL": config.result_url,
        "Occasion": occasion[:100],
    }
    try:
        response = requests.post(
            B2C_URL,
            json=payload,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
    except requests.RequestException as error:
        raise DarajaSubmissionUncertain(
            "The sandbox submission response was not received."
        ) from error

    if 400 <= response.status_code < 500:
        raise DarajaRejected(
            f"Daraja sandbox rejected the payout (HTTP {response.status_code})."
        )
    if response.status_code >= 500:
        raise DarajaSubmissionUncertain(
            "Daraja sandbox returned a server error after the payout was submitted."
        )
    try:
        result = response.json()
    except ValueError as error:
        raise DarajaSubmissionUncertain(
            "Daraja sandbox returned an unreadable submission response."
        ) from error
    if not isinstance(result, dict):
        raise DarajaSubmissionUncertain(
            "Daraja sandbox returned an invalid submission response."
        )

    response_code = result.get("ResponseCode")
    if response_code is not None and str(response_code) != "0":
        description = result.get("ResponseDescription") or "Submission was rejected."
        raise DarajaRejected(str(description)[:300])

    conversation_id = result.get("ConversationID")
    originator_conversation_id = result.get("OriginatorConversationID")
    if not conversation_id or not originator_conversation_id:
        raise DarajaSubmissionUncertain(
            "Daraja accepted or may have accepted the payout, but returned no "
            "correlation identifiers. Reconcile before retrying."
        )
    return {
        "conversation_id": str(conversation_id),
        "originator_conversation_id": str(originator_conversation_id),
        "message": str(result.get("ResponseDescription") or "Payout submitted."),
    }
