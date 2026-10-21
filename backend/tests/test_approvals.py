"""Tests for the approvals endpoints.

These run against the real PostgreSQL database in DATABASE_URL. Each test
creates its own throwaway users and approvals and removes them afterwards.
They are skipped if DATABASE_URL is not set or the database is not running.

Run:  pytest tests/test_approvals.py -v
"""

import os
import uuid

import psycopg
import pytest

from backend.app import create_app
from backend.db import connect_database
from backend.services.approvals import (
    REQUEST_TYPES,
    create_approval,
    has_viewed_pending,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL is not set"
)

ROLES = ("admin", "manager", "staff")
MISSING_ID = 2_000_000_000


@pytest.fixture(scope="module")
def app():
    try:
        application = create_app(secret_key="test-secret-key")
    except psycopg.OperationalError as error:
        pytest.skip(f"Database is not available: {error}")
    application.config.update(TESTING=True)
    return application


def _cleanup(user_ids, approval_ids):
    with connect_database() as connection:
        if approval_ids:
            connection.execute(
                "DELETE FROM \"Audit_Log\" WHERE entity_type = 'approval' "
                "AND entity_id = ANY(%s)",
                (approval_ids,),
            )
            connection.execute(
                'DELETE FROM "Approval_Items" WHERE approval_id = ANY(%s)', (approval_ids,)
            )
        connection.execute('DELETE FROM "Users" WHERE user_id = ANY(%s)', (user_ids,))


@pytest.fixture
def people(app):
    """One throwaway user per role, each with a logged-in test client."""
    tag = uuid.uuid4().hex[:8]
    ids, clients, approvals = {}, {}, []
    with connect_database() as connection:
        for role in ROLES:
            username = f"t_{role}_{tag}"
            ids[role] = connection.execute(
                'INSERT INTO "Users" (username, email, password_hash, role) '
                "VALUES (%s, %s, %s, %s) RETURNING user_id",
                (username, f"{username}@example.com", "not-a-real-hash", role),
            ).fetchone()["user_id"]
    for role, user_id in ids.items():
        client = app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
        clients[role] = client
    try:
        yield {"tag": tag, "ids": ids, "clients": clients, "approvals": approvals}
    finally:
        _cleanup(list(ids.values()), approvals)


def _make(people, request_type="equipment_assignment"):
    with connect_database() as connection:
        row = create_approval(
            connection,
            request_type,
            people["ids"]["staff"],
            f"Test {request_type} {people['tag']}",
            reference_id=1,
        )
    people["approvals"].append(row["approval_id"])
    return row["approval_id"]


def _row(approval_id):
    with connect_database() as connection:
        return connection.execute(
            'SELECT * FROM "Approval_Items" WHERE approval_id = %s', (approval_id,)
        ).fetchone()


def _decide(client, approval_id, **body):
    return client.post(f"/approvals/{approval_id}/decision", json=body)


# ---------------------------------------------------------------------------
# Who can use the endpoints (T16)
# ---------------------------------------------------------------------------
def test_login_is_required(app):
    anonymous = app.test_client()
    assert anonymous.get("/approvals/pending").status_code == 401
    assert _decide(anonymous, 1, decision="approved").status_code == 401


def test_staff_are_rejected_by_the_server(people):
    approval_id = _make(people)
    staff = people["clients"]["staff"]
    assert staff.get("/approvals/pending").status_code == 403
    assert _decide(staff, approval_id, decision="approved").status_code == 403
    assert _row(approval_id)["status"] == "pending"


# ---------------------------------------------------------------------------
# Which requests each role sees (T5, T6)
# ---------------------------------------------------------------------------
def test_each_role_sees_only_its_own_request_types(people):
    made = {request_type: _make(people, request_type) for request_type in REQUEST_TYPES}

    def seen(role):
        response = people["clients"][role].get("/approvals/pending")
        assert response.status_code == 200
        return {
            item["request_type"]
            for item in response.get_json()["approvals"]
            if item["approval_id"] in made.values()
        }

    everything_but_tools = set(REQUEST_TYPES) - {"tool_assignment"}
    assert seen("admin") == everything_but_tools
    assert seen("manager") == everything_but_tools


def test_decided_requests_leave_the_pending_list(people):
    approval_id = _make(people)
    admin = people["clients"]["admin"]

    def pending_ids():
        return {a["approval_id"] for a in admin.get("/approvals/pending").get_json()["approvals"]}

    assert approval_id in pending_ids()
    assert _decide(admin, approval_id, decision="approved").status_code == 200
    assert approval_id not in pending_ids()


def test_pending_list_shows_who_asked(people):
    approval_id = _make(people)
    items = people["clients"]["admin"].get("/approvals/pending").get_json()["approvals"]
    mine = next(item for item in items if item["approval_id"] == approval_id)
    assert mine["requested_by"] == people["ids"]["staff"]
    assert mine["summary"].startswith("Test equipment_assignment")


# ---------------------------------------------------------------------------
# Approve and reject (T7, T17)
# ---------------------------------------------------------------------------
def test_approving_records_who_and_when(people):
    approval_id = _make(people)
    response = _decide(people["clients"]["manager"], approval_id, decision="approved")
    assert response.status_code == 200
    assert response.get_json()["approval"]["status"] == "approved"

    row = _row(approval_id)
    assert row["status"] == "approved"
    assert row["decided_by"] == people["ids"]["manager"]
    assert row["decided_at"] is not None
    with connect_database() as connection:
        notification = connection.execute(
            'SELECT message, notif_type FROM "Notifications" WHERE user_id = %s '
            "ORDER BY notification_id DESC LIMIT 1",
            (people["ids"]["staff"],),
        ).fetchone()
    assert notification["notif_type"] == "approval_decision"
    assert "equipment assignment request #1 was approved" in notification["message"]
    visible_notifications = people["clients"]["staff"].get("/notifications").get_json()[
        "notifications"
    ]
    assert any(
        item["notif_type"] == "approval_decision"
        and "was approved" in item["message"]
        for item in visible_notifications
    )


def test_rejecting_requires_a_reason(people):
    approval_id = _make(people)
    admin = people["clients"]["admin"]

    assert _decide(admin, approval_id, decision="rejected").status_code == 422
    assert _decide(admin, approval_id, decision="rejected", reason="   ").status_code == 422
    assert _row(approval_id)["status"] == "pending"

    response = _decide(admin, approval_id, decision="rejected", reason="Over budget")
    assert response.status_code == 200
    row = _row(approval_id)
    assert row["status"] == "rejected"
    assert row["decision_reason"] == "Over budget"
    with connect_database() as connection:
        notification = connection.execute(
            'SELECT message FROM "Notifications" WHERE user_id = %s '
            "ORDER BY notification_id DESC LIMIT 1",
            (people["ids"]["staff"],),
        ).fetchone()
    assert "was rejected. Reason: Over budget" in notification["message"]


@pytest.mark.parametrize("body", [{}, {"decision": "maybe"}, {"decision": 5}])
def test_invalid_decisions_are_rejected(people, body):
    approval_id = _make(people)
    response = _decide(people["clients"]["admin"], approval_id, **body)
    assert response.status_code == 422
    assert _row(approval_id)["status"] == "pending"


def test_body_must_be_json(people):
    approval_id = _make(people)
    response = people["clients"]["admin"].post(
        f"/approvals/{approval_id}/decision", data="not json", content_type="text/plain"
    )
    assert response.status_code == 422


def test_a_request_can_only_be_decided_once(people):
    approval_id = _make(people)
    assert _decide(people["clients"]["admin"], approval_id, decision="approved").status_code == 200

    second = _decide(people["clients"]["manager"], approval_id, decision="rejected", reason="Too late")
    assert second.status_code == 409
    row = _row(approval_id)
    assert row["status"] == "approved"
    assert row["decided_by"] == people["ids"]["admin"]


def test_roles_cannot_decide_types_they_do_not_see(people):
    escalation = _make(people, "escalation")
    tool = _make(people, "tool_assignment")

    assert _decide(people["clients"]["manager"], escalation, decision="approved").status_code == 200
    assert _decide(people["clients"]["admin"], tool, decision="approved").status_code == 403
    assert _row(escalation)["status"] == "approved"
    assert _row(tool)["status"] == "pending"


def test_unknown_approval_returns_404(people):
    assert _decide(people["clients"]["admin"], MISSING_ID, decision="approved").status_code == 404


# ---------------------------------------------------------------------------
# Audit log (T20) and the manager's view (T8)
# ---------------------------------------------------------------------------
def test_requests_and_decisions_are_audited(people):
    approved, rejected = _make(people), _make(people)
    _decide(people["clients"]["admin"], approved, decision="approved")
    _decide(people["clients"]["manager"], rejected, decision="rejected", reason="Not needed")

    def trail(approval_id):
        with connect_database() as connection:
            rows = connection.execute(
                'SELECT action, user_id FROM "Audit_Log" '
                "WHERE entity_type = 'approval' AND entity_id = %s ORDER BY audit_id",
                (approval_id,),
            ).fetchall()
        return [(row["action"], row["user_id"]) for row in rows]

    staff_id = people["ids"]["staff"]
    assert trail(approved) == [
        ("approval_requested", staff_id),
        ("approval_approved", people["ids"]["admin"]),
    ]
    assert trail(rejected) == [
        ("approval_requested", staff_id),
        ("approval_rejected", people["ids"]["manager"]),
    ]


def test_manager_opening_the_list_is_recorded(people):
    manager_id = people["ids"]["manager"]
    with connect_database() as connection:
        assert has_viewed_pending(connection, manager_id) is False

    people["clients"]["admin"].get("/approvals/pending")
    with connect_database() as connection:
        assert has_viewed_pending(connection, manager_id) is False

    people["clients"]["manager"].get("/approvals/pending")
    with connect_database() as connection:
        assert has_viewed_pending(connection, manager_id) is True


# ---------------------------------------------------------------------------
# create_approval, used by other modules
# ---------------------------------------------------------------------------
def test_create_approval_validates_its_input(people):
    with connect_database() as connection:
        with pytest.raises(ValueError):
            create_approval(connection, "not_a_type", people["ids"]["staff"], "x")
        with pytest.raises(ValueError):
            create_approval(connection, "escalation", people["ids"]["staff"], "   ")