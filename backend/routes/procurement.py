"""Procurement routes: buying items the store does not have.

Only managers can see or use these endpoints: the server checks the role on
every call, whatever the page shows. A procurement
starts as a draft (often created automatically from an unavailable asset
request), is filled in, then submitted for approval. Items must already exist
in the inventory (T11). Every response includes the procurement's history (the
status timeline), and every action is written to the audit log (T20).

Errors: 401 not signed in, 403 wrong role, 404 not found, 409 not allowed in
the current state, 422 validation failed.

Register in app.py:
    app.register_blueprint(procurement_bp, url_prefix="/procurements")
"""

from decimal import Decimal, InvalidOperation

import psycopg
from flask import Blueprint, jsonify, request, session

from ..auth import roles_required
from ..db import connect_database
from ..services.approvals import create_approval
from ..services.request_workflow import (
    attach_history,
    convert_to_procurement,
    find_inventory_item,
    log_action,
    record_event,
)

procurement_bp = Blueprint("procurement", __name__)

PROCUREMENT = '"Procurements"'
REQUESTS = '"Requests"'
USERS = '"Users"'
DISBURSEMENTS = '"Disbursements"'

READ_ROLES = ("manager",)
WRITE_ROLES = ("manager",)

PROCUREMENT_STATUSES = {
    "draft", "pending", "pending_approval", "level_1", "level_2",
    "approved", "rejected", "purchased", "cancelled",
}
# Task T10: "unapproved" means still waiting for a decision.
OPEN_STATUSES = ("draft", "pending", "pending_approval", "level_1", "level_2")
# ...and "unpaid" means no disbursement for it has been paid.
PAID_DISBURSEMENT_STATUSES = ("paid", "success")

ASSET_TYPES = {"tool", "device", "vehicle"}
CONVERTIBLE_REQUEST_STATUSES = ("pending", "approved")
MAX_COST = Decimal("9999999999.99")  # fits NUMERIC(12,2)
MAX_QUANTITY = 1_000_000
OPTIONAL_TEXT = ("category", "supplier", "reason")  # a blank value means "not given"
TEXT_LIMITS = {"item_name": 150, "category": 100, "supplier": 150, "reason": 2000}
NOT_IN_INVENTORY = (
    "That item is not in the inventory. Procurement is only for items that exist there."
)

# action -> (statuses it can start from, status it moves to, history note, audit action)
ACTIONS = {
    "submit": (("draft",), "pending_approval", "Sent to approver.", "procurement_submitted"),
    "cancel": (("draft", "pending_approval"), "cancelled", "Cancelled.", "procurement_cancelled"),
    "purchased": (("approved",), "purchased", "Marked as purchased.", "procurement_purchased"),
}

PROCUREMENT_SELECT = f"""
SELECT p.procurement_id, p.request_id, p.requested_by AS raised_by, u.username AS raised_by_name,
       p.item_name, p.asset_type, p.category, p.quantity, p.estimated_cost,
       p.supplier, p.reason, p.status, p.created_at, p.updated_at
FROM {PROCUREMENT} p
JOIN {USERS} u ON u.user_id = p.requested_by
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error(message, status):
    return jsonify(error=message), status


def _invalid(message):
    """Validation failed (task T19: 422)."""
    return _error(message, 422)


def _payload():
    data = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    return data if isinstance(data, dict) else {}


def _int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cost(value):
    """Return a Decimal of 0 or more with two places, or None if invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        cost = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    if not cost.is_finite() or cost < 0 or cost > MAX_COST:
        return None
    return cost.quantize(Decimal("0.01"))


def _clean_fields(data):
    """Validate the editable fields that are present. Returns (fields, error)."""
    fields = {}
    for key, limit in TEXT_LIMITS.items():
        if data.get(key) is None:
            continue
        value = data[key]
        if key in OPTIONAL_TEXT and isinstance(value, str) and not value.strip():
            continue
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            return None, f"{key} must be non-empty text of at most {limit} characters."
        fields[key] = value.strip()
    if data.get("asset_type") is not None:
        if data["asset_type"] not in ASSET_TYPES:
            return None, "asset_type must be one of: tool, device, vehicle."
        fields["asset_type"] = data["asset_type"]
    if data.get("quantity") is not None:
        quantity = _int(data["quantity"])
        if quantity is None or quantity < 1 or quantity > MAX_QUANTITY:
            return None, f"quantity must be a whole number from 1 to {MAX_QUANTITY}."
        fields["quantity"] = quantity
    if data.get("estimated_cost") is not None:
        cost = _cost(data["estimated_cost"])
        if cost is None:
            return None, "estimated_cost must be a number of 0 or more."
        fields["estimated_cost"] = cost
    return fields, None


def _audit_details(fields):
    """Make the changed fields safe to store as JSON."""
    return {key: (str(value) if isinstance(value, Decimal) else value)
            for key, value in fields.items()}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@procurement_bp.get("")
@roles_required(*READ_ROLES)
def list_procurements():
    """List procurements, newest first. Optional ?status= filter."""
    status = request.args.get("status")
    if status is not None and status not in PROCUREMENT_STATUSES:
        return _invalid("Unknown status filter.")

    where, params = ("WHERE p.status = %s", (status,)) if status else ("", ())
    with connect_database() as connection:
        rows = connection.execute(
            f"{PROCUREMENT_SELECT} {where} "
            "ORDER BY p.created_at DESC, p.procurement_id DESC LIMIT 200",
            params,
        ).fetchall()
        attach_history(connection, "procurement", rows, "procurement_id")
    return jsonify(procurements=rows), 200


@procurement_bp.get("/open")
@roles_required(*READ_ROLES)
def list_open_procurements():
    """Task T10: procurements that are still unapproved and have not been paid."""
    with connect_database() as connection:
        rows = connection.execute(
            f"""{PROCUREMENT_SELECT}
                WHERE p.status = ANY(%s)
                  AND NOT EXISTS (
                      SELECT 1 FROM {DISBURSEMENTS} d
                      WHERE d.procurement_id = p.procurement_id AND d.status = ANY(%s))
                ORDER BY p.created_at DESC, p.procurement_id DESC LIMIT 200""",
            (list(OPEN_STATUSES), list(PAID_DISBURSEMENT_STATUSES)),
        ).fetchall()
        attach_history(connection, "procurement", rows, "procurement_id")
    return jsonify(procurements=rows), 200


@procurement_bp.get("/<int:procurement_id>")
@roles_required(*READ_ROLES)
def get_procurement(procurement_id):
    """Return one procurement."""
    with connect_database() as connection:
        row = connection.execute(
            f"{PROCUREMENT_SELECT} WHERE p.procurement_id = %s", (procurement_id,)
        ).fetchone()
        if row is None:
            return _error("Procurement not found.", 404)
        attach_history(connection, "procurement", [row], "procurement_id")
    return jsonify(procurement=row), 200


@procurement_bp.post("")
@roles_required(*WRITE_ROLES)
def create_procurement():
    """Create a draft procurement, directly or from an unfulfilled asset request.

    Body: item_name or asset_id (the item must exist in the inventory), asset_type,
    category, quantity, estimated_cost, supplier, reason, and optionally request_id.
    """
    data = _payload()
    user_id = session["user_id"]
    fields, problem = _clean_fields(data)
    if problem:
        return _invalid(problem)

    asset_id = None
    if data.get("asset_id") is not None:
        asset_id = _int(data["asset_id"])
        if asset_id is None:
            return _invalid("asset_id must be a number.")

    request_id = None
    if data.get("request_id") is not None:
        request_id = _int(data["request_id"])
        if request_id is None:
            return _invalid("request_id must be a number.")
    elif "item_name" not in fields and asset_id is None:
        return _invalid("item_name or asset_id is required.")

    try:
        with connect_database() as connection:
            if request_id is not None:
                found = connection.execute(
                    f"SELECT request_type, status, asset_id, item_name FROM {REQUESTS} "
                    "WHERE request_id = %s FOR UPDATE",
                    (request_id,),
                ).fetchone()
                if found is None:
                    return _error("Request not found.", 404)
                if found["request_type"] != "asset":
                    return _invalid("Only asset requests can become a procurement.")
                if found["status"] not in CONVERTIBLE_REQUEST_STATUSES:
                    return _error(f"A {found['status']} request cannot be converted.", 409)
                # The item is whatever the manager names, else the request's own.
                if asset_id is None and "item_name" not in fields:
                    asset_id = found["asset_id"]
                item_name = fields.get("item_name") or found["item_name"]
            else:
                item_name = fields.get("item_name")

            item = find_inventory_item(connection, asset_id=asset_id, item_name=item_name)
            if item is None:
                return _invalid(NOT_IN_INVENTORY)
            fields["item_name"] = item["name"]
            fields.setdefault("asset_type", item["asset_type"])
            if item["category"]:
                fields.setdefault("category", item["category"])

            if request_id is not None:
                created = convert_to_procurement(
                    connection, request_id, raised_by=user_id, actor_id=user_id,
                    request_note="Manager raised a procurement request.",
                    **fields,
                )
            else:
                created = connection.execute(
                    f"""
                    INSERT INTO {PROCUREMENT}
                        (requested_by, item_name, asset_type, category, quantity,
                         estimated_cost, supplier, reason, status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'draft')
                    RETURNING procurement_id
                    """,
                    (user_id, fields["item_name"], fields.get("asset_type"),
                     fields.get("category"), fields.get("quantity", 1),
                     fields.get("estimated_cost"), fields.get("supplier"),
                     fields.get("reason")),
                ).fetchone()
                record_event(
                    connection, "procurement", created["procurement_id"], "draft",
                    "Procurement request created.", user_id,
                )
                log_action(
                    connection, user_id, "procurement_created", "procurement",
                    created["procurement_id"],
                    {"item_name": fields["item_name"], "source": "direct",
                     **_audit_details({k: v for k, v in fields.items()
                                       if k in ("quantity", "estimated_cost")})},
                )
            row = connection.execute(
                f"{PROCUREMENT_SELECT} WHERE p.procurement_id = %s",
                (created["procurement_id"],),
            ).fetchone()
            attach_history(connection, "procurement", [row], "procurement_id")
    except psycopg.errors.UniqueViolation:
        return _error("That request already has a procurement.", 409)

    return jsonify(procurement=row), 201


@procurement_bp.patch("/<int:procurement_id>")
@roles_required(*WRITE_ROLES)
def update_procurement(procurement_id):
    """Edit a draft and/or move it along.

    Body: any editable field (drafts only) and optionally "action":
      submit    draft -> pending_approval (needs an estimated_cost above 0)
      cancel    draft or pending_approval -> cancelled
      purchased approved -> purchased
    """
    data = _payload()
    user_id = session["user_id"]
    fields, problem = _clean_fields(data)
    if problem:
        return _invalid(problem)

    action = data.get("action")
    if action is not None and action not in ACTIONS:
        return _invalid("action must be one of: submit, cancel, purchased.")
    if not fields and action is None:
        return _invalid("Nothing to update.")

    with connect_database() as connection:
        current = connection.execute(
            f"SELECT status, estimated_cost, item_name FROM {PROCUREMENT} "
            "WHERE procurement_id = %s FOR UPDATE",
            (procurement_id,),
        ).fetchone()
        if current is None:
            return _error("Procurement not found.", 404)

        if fields and current["status"] != "draft":
            return _error("Only draft procurements can be edited.", 409)

        # Re-check the inventory only when the item is being changed, so a draft
        # that was created from a request can still be completed (cost, supplier).
        if "item_name" in fields and (
            fields["item_name"].strip().lower() != current["item_name"].strip().lower()
        ):
            item = find_inventory_item(connection, item_name=fields["item_name"])
            if item is None:
                return _invalid(NOT_IN_INVENTORY)
            fields["item_name"] = item["name"]

        new_status = None
        note = None
        audit_action = None
        if action is not None:
            allowed_from, new_status, note, audit_action = ACTIONS[action]
            if current["status"] not in allowed_from:
                return _error(
                    f"A {current['status']} procurement cannot use the '{action}' action.", 409
                )
            if action == "submit":
                cost = fields.get("estimated_cost", current["estimated_cost"])
                if cost is None or cost <= 0:
                    return _invalid("Add an estimated_cost above 0 before submitting.")

        sets = [f"{column} = %s" for column in fields]
        params = list(fields.values())
        if new_status:
            sets.append("status = %s")
            params.append(new_status)
        sets.append("updated_at = NOW()")
        connection.execute(
            f"UPDATE {PROCUREMENT} SET {', '.join(sets)} WHERE procurement_id = %s",
            (*params, procurement_id),
        )
        if fields:
            record_event(
                connection, "procurement", procurement_id, current["status"],
                "Details updated.", user_id,
            )
            log_action(
                connection, user_id, "procurement_updated", "procurement", procurement_id,
                {"fields": _audit_details(fields)},
            )
        if new_status:
            record_event(connection, "procurement", procurement_id, new_status, note, user_id)
            log_action(
                connection, user_id, audit_action, "procurement", procurement_id,
                {"from": current["status"], "to": new_status},
            )
        if action == "submit":
            item = connection.execute(
                f"SELECT item_name, quantity, estimated_cost FROM {PROCUREMENT} "
                "WHERE procurement_id = %s",
                (procurement_id,),
            ).fetchone()
            create_approval(
                connection,
                "equipment_procurement",
                user_id,
                f"Procurement #{procurement_id}: {item['quantity']} x {item['item_name']}, "
                f"estimated KES {item['estimated_cost']:,.2f}"[:500],
                reference_id=procurement_id,
            )
        # TODO: notify the approver once notifications exist.
        row = connection.execute(
            f"{PROCUREMENT_SELECT} WHERE p.procurement_id = %s", (procurement_id,)
        ).fetchone()
        attach_history(connection, "procurement", [row], "procurement_id")

    return jsonify(procurement=row), 200