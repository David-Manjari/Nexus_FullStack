# checks the 401, 403, 404, 405 and 422 cases

import os
import uuid

import pytest

from backend.app import create_app
from backend.db import connect_database

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"
)


@pytest.fixture(scope="module")
def app():
    application = create_app(secret_key="test-secret-key")
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def clients(app):
    # test client for a staff user/manager
    tag = uuid.uuid4().hex[:8]
    ids, made = [], {}
    with connect_database() as connection:
        for role in ("staff", "manager"):
            username = f"t_err_{role}_{tag}"
            user_id = connection.execute(
                'INSERT INTO "Users" (username, email, password_hash, role) '
                "VALUES (%s, %s, %s, %s) RETURNING user_id",
                (username, f"{username}@example.com", "not-a-real-hash", role),
            ).fetchone()["user_id"]
            ids.append(user_id)
            client = app.test_client()
            with client.session_transaction() as session:
                session["user_id"] = user_id
            made[role] = client
    try:
        yield made
    finally:
        with connect_database() as connection:
            connection.execute('DELETE FROM "Users" WHERE user_id = ANY(%s)', (ids,))


def _assert_error(response, status):
    assert response.status_code == status
    body = response.get_json()
    assert isinstance(body, dict)
    assert isinstance(body.get("error"), str) and body["error"]


def test_unauthenticated_is_401(app):
    _assert_error(app.test_client().get("/requests"), 401)


def test_unknown_path_is_a_json_404(app):
    _assert_error(app.test_client().get("/no-such-page"), 404)


def test_wrong_method_is_a_json_405(app):
    _assert_error(app.test_client().delete("/health"), 405)


def test_validation_failure_is_422(clients):
    _assert_error(clients["staff"].post("/requests", json={}), 422)
    _assert_error(clients["manager"].post("/api/disbursements", json={}), 422)


def test_wrong_role_is_403(clients):
    _assert_error(clients["staff"].post("/api/disbursements", json={}), 403)