import os
import time
import uuid

import pytest
from werkzeug.security import generate_password_hash

from backend.app import create_app
from backend.db import connect_database
from backend.mfa import _totp


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


def test_required_mfa_enrollment_login_and_single_use_recovery(account):
    client, username, password, user_id = account
    login = _login(client, username, password)
    assert login.status_code == 200
    setup = login.get_json()["setup"]
    assert login.get_json()["mfa_setup_required"] is True
    assert client.get("/notifications").status_code == 401

    verified = client.post(
        "/session/2fa/verify", json={"code": _current_code(setup["secret"])}
    )
    assert verified.status_code == 200
    recovery_codes = verified.get_json()["recovery_codes"]
    assert len(recovery_codes) == 10
    assert client.get("/session/me").status_code == 200
    assert client.get("/notifications").status_code == 200

    with connect_database() as connection:
        stored = connection.execute(
            '''SELECT mfa_enabled, mfa_secret, mfa_recovery_hashes
               FROM "Users" WHERE user_id = %s''',
            (user_id,),
        ).fetchone()
    assert stored["mfa_enabled"] is True
    assert stored["mfa_secret"] != setup["secret"]
    assert setup["secret"] not in str(stored["mfa_recovery_hashes"])

    client.post("/session/logout")
    login = _login(client, username, password)
    assert login.status_code == 200
    assert login.get_json()["mfa_setup_required"] is False
    assert "setup" not in login.get_json()

    recovery_login = client.post(
        "/session/2fa/verify", json={"code": recovery_codes[0]}
    )
    assert recovery_login.status_code == 200
    client.post("/session/logout")

    login = _login(client, username, password)
    assert login.status_code == 200
    reused_code = client.post(
        "/session/2fa/verify", json={"code": recovery_codes[0]}
    )
    assert reused_code.status_code == 401
    assert client.get("/notifications").status_code == 401


def test_mfa_challenge_expires(account):
    client, username, password, user_id = account
    login = _login(client, username, password)
    secret = login.get_json()["setup"]["secret"]
    with connect_database() as connection:
        connection.execute(
            '''UPDATE "Users" SET mfa_pending_expires_at = NOW() - INTERVAL '1 second'
               WHERE user_id = %s''',
            (user_id,),
        )

    response = client.post(
        "/session/2fa/verify", json={"code": _current_code(secret)}
    )
    assert response.status_code == 401
    assert client.get("/notifications").status_code == 401


def test_a_new_login_invalidates_the_previous_mfa_challenge(account):
    client, username, password, _ = account
    other_client = client.application.test_client()
    first_setup = _login(client, username, password).get_json()["setup"]
    second_setup = _login(other_client, username, password).get_json()["setup"]

    stale_challenge = client.post(
        "/session/2fa/verify", json={"code": _current_code(first_setup["secret"])}
    )
    assert stale_challenge.status_code == 401

    valid_challenge = other_client.post(
        "/session/2fa/verify", json={"code": _current_code(second_setup["secret"])}
    )
    assert valid_challenge.status_code == 200


def test_repeated_invalid_codes_are_temporarily_locked(account):
    client, username, password, _ = account
    login = _login(client, username, password)
    secret = login.get_json()["setup"]["secret"]
    for attempt in range(5):
        response = client.post(
            "/session/2fa/verify",
            json={"code": "invalid"},
        )
        assert response.status_code == (429 if attempt == 4 else 401)
    assert client.post(
        "/session/2fa/verify", json={"code": _current_code(secret)}
    ).status_code == 429
