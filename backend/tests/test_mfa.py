import os
import time
import uuid
import hashlib
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.db import connect_database
from backend.mfa import _totp, build_totp_uri
from backend.routes import sessions


pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"
)


@pytest.fixture
def account():
    tag = uuid.uuid4().hex[:10]
    username = f"mfa_{tag}"
    password = "Strong-Pass1!"
    application = create_app(secret_key="mfa-test-secret")
    application.config.update(TESTING=True)
    client = application.test_client()
    with connect_database() as connection:
        user_id = connection.execute(
            '''INSERT INTO "Users" (username, email, password_hash, role)
               VALUES (%s, %s, %s, 'staff') RETURNING user_id''',
            (username, f"{username}@example.com", generate_password_hash(password)),
        ).fetchone()["user_id"]
    try:
        yield client, username, password, user_id
    finally:
        with connect_database() as connection:
            connection.execute('DELETE FROM "Users" WHERE user_id = %s', (user_id,))


def _current_code(secret):
    return _totp(secret, int(time.time() // 30))


def _login(client, username, password):
    return client.post(
        "/session/login",
        json={"identifier": username, "password": password},
    )


def test_qr_sign_in_and_totp_backup_enrollment(account):
    client, username, password, user_id = account
    login = _login(client, username, password)
    assert login.status_code == 200
    qr_code = login.get_json()["qr_code"]
    assert qr_code.isdigit() and len(qr_code) == 6
    assert client.get("/notifications").status_code == 401

    verified = client.post(
        "/session/2fa/verify", json={"method": "qr", "code": qr_code}
    )
    assert verified.status_code == 200
    recovery_codes = verified.get_json()["recovery_codes"]
    assert len(recovery_codes) == 10
    assert client.get("/session/me").status_code == 200
    assert client.get("/notifications").status_code == 200

    with connect_database() as connection:
        stored = connection.execute(
            '''SELECT mfa_enabled, mfa_secret, mfa_recovery_hashes,
                      mfa_totp_enabled
               FROM "Users" WHERE user_id = %s''',
            (user_id,),
        ).fetchone()
    assert stored["mfa_enabled"] is True
    assert stored["mfa_secret"] is None
    assert stored["mfa_totp_enabled"] is False
    assert all(code not in str(stored["mfa_recovery_hashes"]) for code in recovery_codes)

    client.post("/session/logout")
    login = _login(client, username, password)
    assert login.status_code == 200
    setup_response = client.post("/session/2fa/totp/setup")
    assert setup_response.status_code == 200
    setup = setup_response.get_json()["setup"]
    assert setup["otpauth_url"].startswith("otpauth://totp/")
    totp_verified = client.post(
        "/session/2fa/verify",
        json={"method": "totp", "code": _current_code(setup["secret"])},
    )
    assert totp_verified.status_code == 200

    client.post("/session/logout")
    assert _login(client, username, password).status_code == 200
    recovery_login = client.post(
        "/session/2fa/verify",
        json={"method": "recovery", "code": recovery_codes[0]},
    )
    assert recovery_login.status_code == 200
    client.post("/session/logout")

    login = _login(client, username, password)
    assert login.status_code == 200
    reused_code = client.post(
        "/session/2fa/verify",
        json={"method": "recovery", "code": recovery_codes[0]},
    )
    assert reused_code.status_code == 401
    assert client.get("/notifications").status_code == 401


def test_mfa_challenge_expires(account):
    client, username, password, user_id = account
    login = _login(client, username, password)
    qr_code = login.get_json()["qr_code"]
    with connect_database() as connection:
        connection.execute(
            '''UPDATE "Users" SET mfa_pending_expires_at = NOW() - INTERVAL '1 second'
               WHERE user_id = %s''',
            (user_id,),
        )

    response = client.post(
        "/session/2fa/verify",
        json={"method": "qr", "code": qr_code},
    )
    assert response.status_code == 401
    assert client.get("/notifications").status_code == 401


def test_a_new_login_invalidates_the_previous_mfa_challenge(account):
    client, username, password, _ = account
    other_client = client.application.test_client()
    first_code = _login(client, username, password).get_json()["qr_code"]
    second_code = _login(other_client, username, password).get_json()["qr_code"]

    stale_challenge = client.post(
        "/session/2fa/verify",
        json={"method": "qr", "code": first_code},
    )
    assert stale_challenge.status_code == 401

    valid_challenge = other_client.post(
        "/session/2fa/verify",
        json={"method": "qr", "code": second_code},
    )
    assert valid_challenge.status_code == 200


def test_repeated_invalid_codes_are_temporarily_locked(account):
    client, username, password, _ = account
    login = _login(client, username, password)
    qr_code = login.get_json()["qr_code"]
    for attempt in range(5):
        response = client.post(
            "/session/2fa/verify",
            json={"method": "qr", "code": "invalid"},
        )
        assert response.status_code == (429 if attempt == 4 else 401)
    assert client.post(
        "/session/2fa/verify",
        json={"method": "qr", "code": qr_code},
    ).status_code == 429


def test_build_totp_uri_encodes_account_and_includes_totp_parameters():
    uri = build_totp_uri("JBSWY3DPEHPK3PXP", "person+work@example.com")
    parsed = urlparse(uri)
    parameters = parse_qs(parsed.query)

    assert parsed.scheme == "otpauth"
    assert parsed.netloc == "totp"
    assert unquote(parsed.path.lstrip("/")) == "Nexus:person+work@example.com"
    assert parameters == {
        "secret": ["JBSWY3DPEHPK3PXP"],
        "issuer": ["Nexus"],
        "algorithm": ["SHA1"],
        "digits": ["6"],
        "period": ["30"],
    }


def test_qr_login_code_completes_sign_in_once(monkeypatch):
    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.user = {
                "user_id": 1,
                "username": "person",
                "email": "person@example.com",
                "role": "staff",
                "is_active": True,
                "mfa_secret": None,
                "mfa_enabled": False,
                "mfa_recovery_hashes": [],
                "mfa_totp_enabled": False,
                "mfa_failed_attempts": 0,
                "locked": False,
                "challenge_valid": True,
                "qr_code_valid": True,
                "mfa_challenge_hash": None,
                "mfa_qr_code_hash": None,
            }
            self.updates = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=()):
            if "SELECT user_id, username, email, role, is_active" in query:
                return Result(self.user)
            self.updates.append((query, params))
            if "mfa_challenge_hash = %s, mfa_qr_code_hash = %s" in query:
                self.user["mfa_challenge_hash"] = params[0]
                self.user["mfa_qr_code_hash"] = params[1]
            return Result()

    connection = Connection()
    monkeypatch.setattr(sessions, "connect_database", lambda: connection)
    monkeypatch.setattr(
        sessions,
        "authenticate_user",
        lambda *_args: {"user_id": 1, "mfa_totp_enabled": False},
    )

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.register_blueprint(sessions.sessions_bp, url_prefix="/session")
    client = app.test_client()

    login_response = client.post(
        "/session/login",
        json={"identifier": "person", "password": "password"},
    )
    qr_code = login_response.json["qr_code"]
    assert login_response.status_code == 200
    assert qr_code.isdigit() and len(qr_code) == 6
    assert login_response.headers["Cache-Control"] == "no-store"

    with client.session_transaction() as browser_session:
        challenge_token = browser_session["mfa_challenge_token"]

    expected_hash = hashlib.sha256(
        f"{challenge_token}:{qr_code}".encode("ascii")
    ).hexdigest()
    assert connection.user["mfa_qr_code_hash"] == expected_hash

    verify_response = client.post(
        "/session/2fa/verify",
        json={"method": "qr", "code": qr_code},
    )
    assert verify_response.status_code == 200
    assert verify_response.json["user"]["user_id"] == 1
    assert verify_response.json["recovery_codes"]
    assert any(
        "mfa_qr_code_hash = NULL" in query
        for query, _params in connection.updates
    )
    replay_response = client.post(
        "/session/2fa/verify",
        json={"method": "qr", "code": qr_code},
    )
    assert replay_response.status_code == 401
