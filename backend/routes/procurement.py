"""Procurement routes: buying items the store does not have.

Store managers and admins create and manage procurements; managers can read
them. A procurement starts as a draft (often created automatically from an
unavailable asset request), is filled in, then submitted for approval.
Every response includes the procurement's history (the status timeline).

Register in app.py:
    app.register_blueprint(procurement_bp, url_prefix="/procurements")
"""

from decimal import Decimal, InvalidOperation

import psycopg
from flask import Blueprint, jsonify, request, session

from ..admin_accounts import connect_database
from ..auth import roles_required
from ..services.request_workflow import (
    attach_history,
    convert_to_procurement,
    record_event,
)

procurement_bp = Blueprint("procurement", __name__)

PROCUREMENT = '"Procurement"'
REQUESTS = '"Requests"'
USERS = '"Users"'

READ_ROLES = ("admin", "manager", "store_manager")
WRITE_ROLES = ("admin", "store_manager")

PROCUREMENT_STATUSES = {
    "draft", "pending_approval", "approved", "rejected", "purchased", "cancelled",
}
ASSET_TYPES = {"tool", "device", "vehicle"}
CONVERTIBLE_REQUEST_STATUSES = ("pending", "approved")
MAX_COST = Decimal("9999999999.99")  # fits NUMERIC(12,2)
TEXT_LIMITS = {"item_name": 150, "category": 100, "supplier": 150, "reason": 2000}

# action -> (statuses it can start from, status it moves to, history note)
ACTIONS = {
    "submit": (("draft",), "pending_approval", "Sent to approver."),
    "cancel": (("draft", "pending_approval"), "cancelled", "Cancelled."),
    "purchased": (("approved",), "purchased", "Marked as purchased."),
}

PROCUREMENT_SELECT = f"""
SELECT p.procurement_id, p.request_id, p.raised_by, u.username AS raised_by_name,
       p.item_name, p.asset_type, p.category, p.quantity, p.estimated_cost,
       p.supplier, p.reason, p.status, p.created_at, p.updated_at
FROM {PROCUREMENT} p
JOIN {USERS} u ON u.user_id = p.raised_by
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error(message, status):
    return jsonify(error=message), status


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
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            return None, f"{key} must be non-empty text of at most {limit} characters."
        fields[key] = value.strip()
    if data.get("asset_type") is not None:
        if data["asset_type"] not in ASSET_TYPES:
            return None, "asset_type must be one of: tool, device, vehicle."
        fields["asset_type"] = data["asset_type"]
    if data.get("quantity") is not None:
        quantity = _int(data["quantity"])
        if quantity is None or quantity < 1:
            return None, "quantity must be a whole number of at least 1."
        fields["quantity"] = quantity
    if data.get("estimated_cost") is not None:
        cost = _cost(data["estimated_cost"])
        if cost is None:
            return None, "estimated_cost must be a number of 0 or more."
        fields["estimated_cost"] = cost
    return fields, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@procurement_bp.get("")
@roles_required(*READ_ROLES)
def list_procurements():
    """List procurements, newest first. Optional ?status= filter."""
    status = request.args.get("status")
    if status is not None and status not in PROCUREMENT_STATUSES:
        return _error("Unknown status filter.", 400)

    where, params = ("WHERE p.status = %s", (status,)) if status else ("", ())
    with connect_database() as connection:
        rows = connection.execute(
            f"{PROCUREMENT_SELECT} {where} "
            "ORDER BY p.created_at DESC, p.procurement_id DESC LIMIT 200",
            params,
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

    Body: item_name (required unless request_id is given), asset_type, category,
    quantity, estimated_cost, supplier, reason, and optionally request_id.
    """
    data = _payload()
    user_id = session["user_id"]
    fields, problem = _clean_fields(data)
    if problem:
        return _error(problem, 400)

    request_id = None
    if data.get("request_id") is not None:
        request_id = _int(data["request_id"])
        if request_id is None:
            return _error("request_id must be a number.", 400)
    elif "item_name" not in fields:
        return _error("item_name is required.", 400)

    try:
        with connect_database() as connection:
            if request_id is not None:
                found = connection.execute(
                    f"SELECT request_type, status FROM {REQUESTS} "
                    "WHERE request_id = %s FOR UPDATE",
                    (request_id,),
                ).fetchone()
                if found is None:
                    return _error("Request not found.", 404)
                if found["request_type"] != "asset":
                    return _error("Only asset requests can become a procurement.", 400)
                if found["status"] not in CONVERTIBLE_REQUEST_STATUSES:
                    return _error(f"A {found['status']} request cannot be converted.", 409)
                created = convert_to_procurement(
                    connection, request_id, raised_by=user_id, actor_id=user_id,
                    request_note="Store manager raised a procurement request.",
                    **fields,
                )
            else:
                created = connection.execute(
                    f"""
                    INSERT INTO {PROCUREMENT}
                        (raised_by, item_name, asset_type, category, quantity,
                         estimated_cost, supplier, reason)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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
        return _error(problem, 400)

    action = data.get("action")
    if action is not None and action not in ACTIONS:
        return _error("action must be one of: submit, cancel, purchased.", 400)
    if not fields and action is None:
        return _error("Nothing to update.", 400)

    with connect_database() as connection:
        current = connection.execute(
            f"SELECT status, estimated_cost FROM {PROCUREMENT} "
            "WHERE procurement_id = %s FOR UPDATE",
            (procurement_id,),
        ).fetchone()
        if current is None:
            return _error("Procurement not found.", 404)

        if fields and current["status"] != "draft":
            return _error("Only draft procurements can be edited.", 409)

        new_status = None
        note = None
        if action is not None:
            allowed_from, new_status, note = ACTIONS[action]
            if current["status"] not in allowed_from:
                return _error(
                    f"A {current['status']} procurement cannot use the '{action}' action.", 409
                )
            if action == "submit":
                cost = fields.get("estimated_cost", current["estimated_cost"])
                if cost is None or cost <= 0:
                    return _error("Add an estimated_cost above 0 before submitting.", 400)

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
        if new_status:
            record_event(connection, "procurement", procurement_id, new_status, note, user_id)
        # TODO: on submit, create the approval record (Member 5) and notify the
        # approver once those exist.
        row = connection.execute(
            f"{PROCUREMENT_SELECT} WHERE p.procurement_id = %s", (procurement_id,)
        ).fetchone()
        attach_history(connection, "procurement", [row], "procurement_id")

    return jsonify(procurement=row), 200
