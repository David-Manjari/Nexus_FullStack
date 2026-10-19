"""Requests and procurement: workflow, roles and the shared database tables.

These tests use the real PostgreSQL database in DATABASE_URL, like the other
test files. Every row they create is removed again at the end of each test.
"""

import uuid

import pytest

from backend.app import create_app
from backend.db import connect_database, init_db


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True)
    return application


@pytest.fixture
def world(app):
    """Create one user per role plus helpers, then clean everything up."""
    tag = uuid.uuid4().hex[:8]
    users = {}
    asset_ids = []
    with connect_database() as connection:
        for role in ("admin", "manager", "store_manager", "staff"):
            row = connection.execute(
                'INSERT INTO "Users" (username, email, password_hash, role) '
                "VALUES (%s, %s, 'x', %s) RETURNING user_id",
                (f"t_{role}_{tag}", f"t_{role}_{tag}@example.com", role),
            ).fetchone()
            users[role] = row["user_id"]

    def client_for(role):
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = users[role]
            sess["role"] = role
        return client

    def make_asset(name, status="available", asset_type="tool"):
        with connect_database() as connection:
            row = connection.execute(
                'INSERT INTO "Assets" (asset_type, name, status, added_by) '
                "VALUES (%s, %s, %s, %s) RETURNING asset_id",
                (asset_type, name, status, users["store_manager"]),
            ).fetchone()
        asset_ids.append(row["asset_id"])
        return row["asset_id"]

    class World:
        pass

    w = World()
    w.tag = tag
    w.users = users
    w.client = client_for
    w.make_asset = make_asset
    w.name = lambda label: f"ZZ{label}-{tag}"
    yield w

    ids = list(users.values())
    with connect_database() as connection:
        connection.execute(
            'DELETE FROM "Request_History" WHERE changed_by = ANY(%s) OR '
            "(entity_type = 'request' AND entity_id IN "
            '(SELECT request_id FROM "Requests" WHERE requester_id = ANY(%s))) OR '
            "(entity_type = 'procurement' AND entity_id IN "
            '(SELECT procurement_id FROM "Procurements" WHERE requested_by = ANY(%s)))',
            (ids, ids, ids),
        )
        connection.execute(
            'DELETE FROM "Disbursements" WHERE procurement_id IN '
            '(SELECT procurement_id FROM "Procurements" WHERE requested_by = ANY(%s))',
            (ids,),
        )
        connection.execute('DELETE FROM "Audit_Log" WHERE user_id = ANY(%s)', (ids,))
        connection.execute('DELETE FROM "Asset_Assignments" WHERE user_id = ANY(%s)', (ids,))
        connection.execute('DELETE FROM "Procurements" WHERE requested_by = ANY(%s)', (ids,))
        connection.execute('DELETE FROM "Requests" WHERE requester_id = ANY(%s)', (ids,))
        connection.execute('DELETE FROM "Assets" WHERE asset_id = ANY(%s)', (asset_ids,))
        connection.execute('DELETE FROM "Users" WHERE user_id = ANY(%s)', (ids,))


def raise_request(client, **body):
    body.setdefault("request_type", "asset")
    body.setdefault("reason", "Needed for site work")
    return client.post("/requests", json=body)


# --- schema -----------------------------------------------------------------
def test_schema_can_be_applied_twice():
    init_db()
    init_db()


def test_old_style_rows_still_work(world):
    """A request written the way the original schema allowed still shows up."""
    with connect_database() as connection:
        row = connection.execute(
            'INSERT INTO "Requests" (requester_id, item_name, reason) '
            "VALUES (%s, %s, 'legacy') RETURNING request_id",
            (world.users["staff"], world.name("legacy")),
        ).fetchone()
    response = world.client("staff").get(f"/requests/{row['request_id']}")
    assert response.status_code == 200
    assert response.get_json()["request"]["request_type"] == "asset"


# --- raising requests -------------------------------------------------------
def test_requires_login(app):
    assert app.test_client().get("/requests").status_code == 401
    assert app.test_client().post("/requests", json={}).status_code == 401


def test_asset_in_stock_waits_for_store_manager(world):
    name = world.name("drill")
    world.make_asset(name)
    response = raise_request(world.client("staff"), item_name=name)
    body = response.get_json()
    assert response.status_code == 201
    assert body["request"]["status"] == "pending"
    assert body["procurement"] is None
    assert body["request"]["requested_by"] == world.users["staff"]
    assert [h["status"] for h in body["request"]["history"]] == ["submitted", "pending"]


def test_asset_out_of_stock_creates_procurement_draft(world):
    name = world.name("missing")
    response = raise_request(world.client("staff"), item_name=name, quantity=2)
    body = response.get_json()
    assert response.status_code == 201
    assert body["request"]["status"] == "converted"
    assert body["procurement"]["status"] == "draft"
    assert body["procurement"]["quantity"] == 2
    assert body["procurement"]["request_id"] == body["request"]["request_id"]
    assert body["procurement"]["raised_by"] == world.users["staff"]


def test_asset_in_maintenance_counts_as_unavailable(world):
    name = world.name("broken")
    world.make_asset(name, status="maintenance")
    body = raise_request(world.client("staff"), item_name=name).get_json()
    assert body["request"]["status"] == "converted"


@pytest.mark.parametrize(
    "body",
    [
        {"request_type": "bogus"},
        {"reason": "   "},
        {"request_type": "asset"},  # no item or asset
        {"request_type": "disbursement"},  # no amount
        {"request_type": "disbursement", "amount": -5},
        {"item_name": "x", "quantity": 0},
        {"item_name": "x", "needed_by": "31/12/2026"},
        {"item_name": "x", "asset_type": "boat"},
    ],
)
def test_bad_requests_are_rejected(world, body):
    payload = {"request_type": "asset", "reason": "r"}
    payload.update(body)
    assert world.client("staff").post("/requests", json=payload).status_code == 422


def test_disbursement_is_escalated_to_a_manager_not_to_self(world):
    response = raise_request(
        world.client("staff"), request_type="disbursement", amount="1500.50"
    )
    request_row = response.get_json()["request"]
    assert response.status_code == 201
    assert request_row["status"] == "escalated"
    with connect_database() as connection:
        approver = connection.execute(
            'SELECT role, user_id FROM "Users" WHERE user_id = %s',
            (request_row["escalated_to"],),
        ).fetchone()
    assert approver["role"] == "manager"
    assert approver["user_id"] != world.users["staff"]


def test_manager_request_goes_to_an_admin(world):
    row = raise_request(
        world.client("manager"), request_type="project", reason="Need a crew"
    ).get_json()["request"]
    with connect_database() as connection:
        role = connection.execute(
            'SELECT role FROM "Users" WHERE user_id = %s', (row["escalated_to"],)
        ).fetchone()["role"]
    assert row["status"] == "escalated"
    assert role == "admin"


# --- who can see what -------------------------------------------------------
def test_visibility_by_role(world):
    name = world.name("visible")
    world.make_asset(name)
    request_id = raise_request(world.client("staff"), item_name=name).get_json()[
        "request"
    ]["request_id"]

    assert world.client("staff").get(f"/requests/{request_id}").status_code == 200
    assert world.client("store_manager").get(f"/requests/{request_id}").status_code == 200
    assert world.client("admin").get(f"/requests/{request_id}").status_code == 200
    # Another staff member and a manager with nothing escalated to them cannot.
    other = world.client("manager")
    assert other.get(f"/requests/{request_id}").status_code == 404

    listed = world.client("staff").get("/requests").get_json()["requests"]
    assert request_id in [r["request_id"] for r in listed]
    listed = other.get("/requests").get_json()["requests"]
    assert request_id not in [r["request_id"] for r in listed]


def test_filters_and_bad_filters(world):
    client = world.client("staff")
    raise_request(client, item_name=world.name("filter"))
    ok = client.get("/requests?status=converted&type=asset")
    assert ok.status_code == 200
    assert all(r["status"] == "converted" for r in ok.get_json()["requests"])
    assert client.get("/requests?status=nonsense").status_code == 422
    assert client.get("/requests?type=nonsense").status_code == 422


# --- fulfilling -------------------------------------------------------------
def test_store_manager_fulfils_and_asset_is_assigned(world):
    name = world.name("laptop")
    asset_id = world.make_asset(name, asset_type="device")
    request_id = raise_request(world.client("staff"), item_name=name).get_json()[
        "request"
    ]["request_id"]

    assert world.client("staff").patch(f"/requests/{request_id}/fulfil").status_code == 403

    response = world.client("store_manager").patch(
        f"/requests/{request_id}/fulfil", json={"asset_id": asset_id}
    )
    assert response.status_code == 200
    assert response.get_json()["request"]["status"] == "fulfilled"
    with connect_database() as connection:
        asset = connection.execute(
            'SELECT status FROM "Assets" WHERE asset_id = %s', (asset_id,)
        ).fetchone()
        assignment = connection.execute(
            'SELECT user_id, request_id FROM "Asset_Assignments" WHERE asset_id = %s',
            (asset_id,),
        ).fetchone()
    assert asset["status"] == "assigned"
    assert assignment["user_id"] == world.users["staff"]
    assert assignment["request_id"] == request_id

    again = world.client("store_manager").patch(f"/requests/{request_id}/fulfil")
    assert again.status_code == 409


def test_cannot_fulfil_an_unavailable_asset_or_a_money_request(world):
    asset_id = world.make_asset(world.name("busy"), status="assigned")
    staff = world.client("staff")
    request_id = raise_request(staff, asset_id=asset_id).get_json()["request"]["request_id"]
    store = world.client("store_manager")
    response = store.patch(f"/requests/{request_id}/fulfil")
    assert response.status_code in (404, 409)

    money = raise_request(staff, request_type="disbursement", amount=10).get_json()
    assert store.patch(f"/requests/{money['request']['request_id']}/fulfil").status_code == 422


# --- procurement ------------------------------------------------------------
def make_procurement(world, label, **extra):
    """Create a draft procurement for a fresh inventory item, as the store manager."""
    name = world.name(label)
    world.make_asset(name)
    body = {"item_name": name}
    body.update(extra)
    response = world.client("store_manager").post("/procurements", json=body)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["procurement"]


def test_only_the_store_manager_can_use_procurement(world):
    """Tasks T9 and T16: enforced on the server for every other role."""
    name = world.name("pump")
    world.make_asset(name)
    payload = {"item_name": name, "quantity": 1}
    pid = make_procurement(world, "guarded")["procurement_id"]
    for role in ("staff", "manager", "admin"):
        client = world.client(role)
        assert client.post("/procurements", json=payload).status_code == 403, role
        assert client.get("/procurements").status_code == 403, role
        assert client.get("/procurements/open").status_code == 403, role
        assert client.get(f"/procurements/{pid}").status_code == 403, role
        assert client.patch(f"/procurements/{pid}", json={"action": "cancel"}).status_code == 403, role


def test_procurement_requires_login(app):
    assert app.test_client().get("/procurements").status_code == 401
    assert app.test_client().post("/procurements", json={}).status_code == 401


def test_store_manager_creates_a_draft(world):
    row = make_procurement(world, "pump", quantity=2)
    assert row["status"] == "draft"
    assert row["quantity"] == 2
    assert row["raised_by"] == world.users["store_manager"]
    assert row["history"][0]["status"] == "draft"


# --- tasks T11 and T17: items must exist in the inventory ----------------------
def test_item_must_exist_in_inventory(world):
    store = world.client("store_manager")
    unknown = store.post("/procurements", json={"item_name": world.name("ghost")})
    assert unknown.status_code == 422
    assert "inventory" in unknown.get_json()["error"]
    assert store.post("/procurements", json={"asset_id": 99999999}).status_code == 422


def test_inventory_name_match_ignores_case_and_uses_the_inventory_name(world):
    name = world.name("Hammer")
    asset_id = world.make_asset(name, asset_type="tool")
    response = world.client("store_manager").post(
        "/procurements", json={"item_name": f"  {name.lower()}  "}
    )
    assert response.status_code == 201
    row = response.get_json()["procurement"]
    assert row["item_name"] == name
    assert row["asset_type"] == "tool"

    by_id = world.client("store_manager").post("/procurements", json={"asset_id": asset_id})
    assert by_id.status_code == 201
    assert by_id.get_json()["procurement"]["item_name"] == name


def test_editing_a_draft_cannot_switch_to_an_unknown_item(world):
    row = make_procurement(world, "edit")
    store = world.client("store_manager")
    bad = store.patch(
        f"/procurements/{row['procurement_id']}", json={"item_name": world.name("nowhere")}
    )
    assert bad.status_code == 422
    other = world.name("other")
    world.make_asset(other)
    good = store.patch(f"/procurements/{row['procurement_id']}", json={"item_name": other})
    assert good.status_code == 200
    assert good.get_json()["procurement"]["item_name"] == other


def test_converting_a_request_to_an_item_outside_the_inventory_is_refused(world):
    name = world.name("pendingitem")
    world.make_asset(name)
    pending = raise_request(world.client("staff"), item_name=name).get_json()["request"]
    refused = world.client("store_manager").post(
        "/procurements",
        json={"request_id": pending["request_id"], "item_name": world.name("elsewhere")},
    )
    assert refused.status_code == 422


# --- task T10: unapproved and unpaid ------------------------------------------
def test_open_list_shows_only_unapproved_and_unpaid(world):
    store = world.client("store_manager")
    draft = make_procurement(world, "open-draft")["procurement_id"]
    approved = make_procurement(world, "open-approved")["procurement_id"]
    paid = make_procurement(world, "open-paid")["procurement_id"]
    with connect_database() as connection:
        connection.execute(
            'UPDATE "Procurements" SET status = \'approved\' WHERE procurement_id = %s',
            (approved,),
        )
        connection.execute(
            'UPDATE "Procurements" SET status = \'pending\' WHERE procurement_id = %s', (paid,)
        )
        connection.execute(
            'INSERT INTO "Disbursements" (procurement_id, amount, status) '
            "VALUES (%s, 100, 'paid')",
            (paid,),
        )
    listed = store.get("/procurements/open")
    assert listed.status_code == 200
    ids = [p["procurement_id"] for p in listed.get_json()["procurements"]]
    assert draft in ids
    assert approved not in ids
    assert paid not in ids


# --- life cycle ---------------------------------------------------------------
def test_procurement_life_cycle(world):
    store = world.client("store_manager")
    pid = make_procurement(world, "saw", quantity=3)["procurement_id"]

    # Cannot submit without a cost, or buy before approval.
    assert store.patch(f"/procurements/{pid}", json={"action": "submit"}).status_code == 422
    assert store.patch(f"/procurements/{pid}", json={"action": "purchased"}).status_code == 409
    assert store.patch(f"/procurements/{pid}", json={}).status_code == 422
    assert store.patch(f"/procurements/{pid}", json={"estimated_cost": -1}).status_code == 422

    edited = store.patch(
        f"/procurements/{pid}", json={"estimated_cost": "250.00", "supplier": "ACME"}
    )
    assert edited.status_code == 200
    submitted = store.patch(f"/procurements/{pid}", json={"action": "submit"})
    assert submitted.get_json()["procurement"]["status"] == "pending_approval"

    # No longer a draft: no edits.
    assert store.patch(f"/procurements/{pid}", json={"supplier": "Other"}).status_code == 409

    statuses = [h["status"] for h in submitted.get_json()["procurement"]["history"]]
    assert statuses == ["draft", "draft", "pending_approval"]

    cancelled = store.patch(f"/procurements/{pid}", json={"action": "cancel"})
    assert cancelled.get_json()["procurement"]["status"] == "cancelled"


def test_purchased_only_after_approval(world):
    store = world.client("store_manager")
    pid = make_procurement(world, "ladder", estimated_cost=40)["procurement_id"]
    with connect_database() as connection:
        connection.execute(
            'UPDATE "Procurements" SET status = \'approved\' WHERE procurement_id = %s',
            (pid,),
        )
    bought = store.patch(f"/procurements/{pid}", json={"action": "purchased"})
    assert bought.get_json()["procurement"]["status"] == "purchased"


def test_manual_procurement_from_a_pending_request(world):
    name = world.name("crate")
    world.make_asset(name)
    request_id = raise_request(world.client("staff"), item_name=name).get_json()[
        "request"
    ]["request_id"]
    store = world.client("store_manager")

    made = store.post("/procurements", json={"request_id": request_id, "estimated_cost": 5})
    assert made.status_code == 201
    assert made.get_json()["procurement"]["item_name"] == name
    assert world.client("staff").get(f"/requests/{request_id}").get_json()["request"][
        "status"
    ] == "converted"

    duplicate = store.post("/procurements", json={"request_id": request_id})
    assert duplicate.status_code == 409
    assert store.post("/procurements", json={"request_id": 99999999}).status_code == 404
    assert store.post("/procurements", json={}).status_code == 422


def test_procurement_filters_and_missing_records(world):
    store = world.client("store_manager")
    make_procurement(world, "filter")
    ok = store.get("/procurements?status=draft")
    assert ok.status_code == 200
    assert all(p["status"] == "draft" for p in ok.get_json()["procurements"])
    assert store.get("/procurements?status=nonsense").status_code == 422
    assert store.get("/procurements/99999999").status_code == 404
    assert store.patch("/procurements/99999999", json={"action": "cancel"}).status_code == 404


# --- task T20: audit log --------------------------------------------------------
def audit_actions(world, role="store_manager"):
    with connect_database() as connection:
        rows = connection.execute(
            'SELECT action, entity_type, entity_id FROM "Audit_Log" '
            "WHERE user_id = %s ORDER BY audit_id",
            (world.users[role],),
        ).fetchall()
    return [(r["action"], r["entity_type"], r["entity_id"]) for r in rows]


def test_every_procurement_action_is_audited(world):
    store = world.client("store_manager")
    pid = make_procurement(world, "audited")["procurement_id"]
    store.patch(f"/procurements/{pid}", json={"estimated_cost": 10})
    store.patch(f"/procurements/{pid}", json={"action": "submit"})
    store.patch(f"/procurements/{pid}", json={"action": "cancel"})
    actions = [a for a, kind, entity in audit_actions(world) if kind == "procurement" and entity == pid]
    assert actions == [
        "procurement_created", "procurement_updated",
        "procurement_submitted", "procurement_cancelled",
    ]


def test_request_actions_are_audited(world):
    name = world.name("audit-drill")
    asset_id = world.make_asset(name)
    request_id = raise_request(world.client("staff"), item_name=name).get_json()["request"][
        "request_id"
    ]
    world.client("store_manager").patch(f"/requests/{request_id}/fulfil", json={"asset_id": asset_id})
    assert ("request_created", "request", request_id) in audit_actions(world, "staff")
    assert ("request_fulfilled", "request", request_id) in audit_actions(world)


def test_a_request_converted_to_procurement_is_audited(world):
    body = raise_request(world.client("staff"), item_name=world.name("audit-missing")).get_json()
    pid = body["procurement"]["procurement_id"]
    assert ("procurement_created", "procurement", pid) in audit_actions(world, "staff")


# --- found by QA: the completion flow and blank form fields ---------------------
def test_a_draft_made_from_an_unknown_item_can_still_be_completed(world):
    """Requests can name any item; the store manager must still be able to finish the draft."""
    name = world.name("unlisted")
    body = raise_request(world.client("staff"), item_name=name).get_json()
    pid = body["procurement"]["procurement_id"]
    store = world.client("store_manager")
    done = store.patch(
        f"/procurements/{pid}",
        json={"item_name": name, "estimated_cost": 90, "supplier": "ACME"},
    )
    assert done.status_code == 200
    assert store.patch(f"/procurements/{pid}", json={"action": "submit"}).status_code == 200


def test_blank_optional_fields_are_treated_as_not_given(world):
    name = world.name("blankform")
    world.make_asset(name)
    response = world.client("store_manager").post(
        "/procurements",
        json={"item_name": name, "supplier": "", "reason": "  ", "category": "",
              "quantity": 1, "estimated_cost": None},
    )
    assert response.status_code == 201
    assert world.client("store_manager").post(
        "/procurements", json={"item_name": "   "}
    ).status_code == 422


def test_huge_numbers_are_rejected_not_crashed(world):
    name = world.name("huge")
    world.make_asset(name)
    store = world.client("store_manager")
    assert store.post("/procurements", json={"item_name": name, "quantity": 10**12}).status_code == 422
    assert raise_request(world.client("staff"), item_name=name, quantity=10**12).status_code == 422
