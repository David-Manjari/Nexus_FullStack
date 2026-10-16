"""Request routes: staff and managers ask for assets, money or project support.

Anyone signed in can raise a request and see their own. Managers also see the
requests escalated to them, store managers see every asset request, and admins
see everything. Only store managers and admins can fulfil an asset request.
Every response includes the request's history (the status timeline).

Register in app.py:
    app.register_blueprint(requests_bp, url_prefix="/requests")
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request, session

from ..admin_accounts import connect_database
from ..auth import roles_required
from ..services.request_workflow import (
    attach_history,
    check_stock,
    convert_to_procurement,
    escalate_request,
    pick_approver,
    record_event,
)

requests_bp = Blueprint("requests", __name__)

REQUESTS = '"Requests"'
ASSETS = '"Assets"'
ASSIGNMENTS = '"Asset_Assignments"'
USERS = '"Users"'

CREATE_ROLES = ("admin", "manager", "store_manager", "staff")
VIEW_ROLES = ("admin", "manager", "store_manager", "staff")
FULFIL_ROLES = ("store_manager", "admin")

REQUEST_TYPES = {"asset", "disbursement", "project"}
ASSET_TYPES = {"tool", "device", "vehicle"}
REQUEST_STATUSES = {
    "pending", "escalated", "approved", "rejected",
    "fulfilled", "converted", "cancelled",
}
FULFILLABLE_STATUSES = ("pending", "approved")
MAX_AMOUNT = Decimal("9999999999.99")  # fits NUMERIC(12,2)

REQUEST_SELECT = f"""
SELECT r.request_id, r.request_type, r.requested_by, u.username AS requester_name,
       r.project_id, r.asset_id, r.asset_type, r.item_name, r.category, r.quantity,
       r.amount, r.needed_by, r.reason, r.status, r.escalated_to, r.fulfilled_by,
       r.created_at, r.updated_at
FROM {REQUESTS} r
JOIN {USERS} u ON u.user_id = r.requested_by
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _error(message, status):
    return jsonify(error=message), status


def _payload():
    data = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    return data if isinstance(data, dict) else {}


def _text(data, key):
    value = data.get(key)
    if isinstance(value, str):
        return value.strip() or None
    return None


def _int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def _amount(value):
    """Return a positive Decimal with two places, or None if invalid."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
        return None
    return amount.quantize(Decimal("0.01"))


def _visibility(role, user_id):
    """SQL condition (and params) limiting which requests this role may see."""
    if role == "admin":
        return "TRUE", ()
    if role == "store_manager":
        return "(r.request_type = 'asset' OR r.requested_by = %s)", (user_id,)
    if role == "manager":
        return "(r.requested_by = %s OR r.escalated_to = %s)", (user_id, user_id)
    return "r.requested_by = %s", (user_id,)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@requests_bp.post("")
@roles_required(*CREATE_ROLES)
def create_request():
    """Raise a request for an asset, a disbursement or project support."""
    data = _payload()
    user_id = session["user_id"]

    request_type = _text(data, "request_type")
    if request_type not in REQUEST_TYPES:
        return _error("request_type must be one of: asset, disbursement, project.", 400)

    reason = _text(data, "reason")
    if reason is None:
        return _error("A reason is required.", 400)

    item_name = _text(data, "item_name")
    category = _text(data, "category")
    if (item_name and len(item_name) > 150) or (category and len(category) > 100):
        return _error("item_name or category is too long.", 400)

    asset_type = _text(data, "asset_type")
    if asset_type is not None and asset_type not in ASSET_TYPES:
        return _error("asset_type must be one of: tool, device, vehicle.", 400)

    quantity = 1 if data.get("quantity") is None else _int(data.get("quantity"))
    if quantity is None or quantity < 1:
        return _error("quantity must be a whole number of at least 1.", 400)

    needed_by = None
    if data.get("needed_by") is not None:
        needed_by = _date(data.get("needed_by"))
        if needed_by is None:
            return _error("needed_by must be a date in YYYY-MM-DD format.", 400)

    asset_id = None
    if data.get("asset_id") is not None:
        asset_id = _int(data.get("asset_id"))
        if asset_id is None:
            return _error("asset_id must be a number.", 400)

    project_id = None
    if data.get("project_id") is not None:
        project_id = _int(data.get("project_id"))
        if project_id is None:
            return _error("project_id must be a number.", 400)

    amount = None
    if request_type == "asset" and asset_id is None and item_name is None:
        return _error("An asset request needs an item_name or an asset_id.", 400)
    if request_type == "disbursement":
        amount = _amount(data.get("amount"))
        if amount is None:
            return _error("A disbursement request needs a positive amount.", 400)

    with connect_database() as connection:
        if asset_id is not None:
            asset = connection.execute(
                f"SELECT asset_type FROM {ASSETS} WHERE asset_id = %s", (asset_id,)
            ).fetchone()
            if asset is None:
                return _error("That asset does not exist.", 400)
            asset_type = asset_type or asset["asset_type"]

        created = connection.execute(
            f"""
            INSERT INTO {REQUESTS}
                (request_type, requested_by, project_id, asset_id, asset_type,
                 item_name, category, quantity, amount, needed_by, reason)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING request_id
            """,
            (request_type, user_id, project_id, asset_id, asset_type, item_name,
             category, quantity, amount, needed_by, reason),
        ).fetchone()
        new_id = created["request_id"]
        record_event(connection, "request", new_id, "submitted", "Request submitted.", user_id)

        procurement = None
        if request_type == "asset":
            # Not in the store? Start a procurement draft automatically.
            stock = check_stock(
                connection, asset_id=asset_id, item_name=item_name,
                category=category, quantity=quantity,
            )
            if stock["available"]:
                record_event(
                    connection, "request", new_id, "pending",
                    "Item available. Sent to the store manager.",
                )
            else:
                procurement = convert_to_procurement(
                    connection, new_id, raised_by=user_id,
                    request_note="Item is not available. Procurement request created.",
                )
        else:
            # Money and project requests go up to an approver.
            approver_id = pick_approver(connection, session["role"], user_id)
            if approver_id is not None:
                escalate_request(connection, new_id, approver_id)
            else:
                record_event(
                    connection, "request", new_id, "pending",
                    "Waiting for an approver to be available.",
                )

        # TODO: notify the approver / store manager once notifications exist.
        row = connection.execute(
            f"{REQUEST_SELECT} WHERE r.request_id = %s", (new_id,)
        ).fetchone()
        attach_history(connection, "request", [row], "request_id")
        if procurement is not None:
            attach_history(connection, "procurement", [procurement], "procurement_id")

    return jsonify(request=row, procurement=procurement), 201


@requests_bp.get("")
@roles_required(*VIEW_ROLES)
def list_requests():
    """List the requests this user is allowed to see, newest first."""
    status = request.args.get("status")
    request_type = request.args.get("type")
    if status is not None and status not in REQUEST_STATUSES:
        return _error("Unknown status filter.", 400)
    if request_type is not None and request_type not in REQUEST_TYPES:
        return _error("Unknown type filter.", 400)

    conditions, params = _visibility(session["role"], session["user_id"])
    conditions = [conditions]
    params = list(params)
    if status:
        conditions.append("r.status = %s")
        params.append(status)
    if request_type:
        conditions.append("r.request_type = %s")
        params.append(request_type)

    with connect_database() as connection:
        rows = connection.execute(
            f"{REQUEST_SELECT} WHERE {' AND '.join(conditions)} "
            "ORDER BY r.created_at DESC, r.request_id DESC LIMIT 200",
            params,
        ).fetchall()
        attach_history(connection, "request", rows, "request_id")

    return jsonify(requests=rows), 200


@requests_bp.get("/<int:request_id>")
@roles_required(*VIEW_ROLES)
def get_request(request_id):
    """Return one request, if this user is allowed to see it."""
    condition, params = _visibility(session["role"], session["user_id"])
    with connect_database() as connection:
        row = connection.execute(
            f"{REQUEST_SELECT} WHERE r.request_id = %s AND {condition}",
            (request_id, *params),
        ).fetchone()
        if row is None:
            return _error("Request not found.", 404)
        attach_history(connection, "request", [row], "request_id")

    return jsonify(request=row), 200


@requests_bp.patch("/<int:request_id>/fulfil")
@roles_required(*FULFIL_ROLES)
def fulfil_request(request_id):
    """Hand an available asset to the person who requested it.

    Body (optional): {"asset_id": 12}. If omitted, the asset named on the
    request is used. If the asset is not available the request is left alone,
    so the store manager can convert it into a procurement instead.
    """
    data = _payload()
    chosen_asset_id = _int(data.get("asset_id")) if data.get("asset_id") is not None else None
    if data.get("asset_id") is not None and chosen_asset_id is None:
        return _error("asset_id must be a number.", 400)

    with connect_database() as connection:
        found = connection.execute(
            f"SELECT request_type, requested_by, asset_id, status FROM {REQUESTS} "
            "WHERE request_id = %s FOR UPDATE",
            (request_id,),
        ).fetchone()
        if found is None:
            return _error("Request not found.", 404)
        if found["request_type"] != "asset":
            return _error("Only asset requests can be fulfilled this way.", 400)
        if found["status"] not in FULFILLABLE_STATUSES:
            return _error(f"A {found['status']} request cannot be fulfilled.", 409)

        asset_id = chosen_asset_id or found["asset_id"]
        if asset_id is None:
            return _error("Choose an asset to hand over (asset_id).", 400)

        asset = connection.execute(
            f"SELECT name, status FROM {ASSETS} WHERE asset_id = %s FOR UPDATE",
            (asset_id,),
        ).fetchone()
        if asset is None:
            return _error("That asset does not exist.", 404)
        if asset["status"] != "available":
            return jsonify(
                error="That asset is not available.",
                asset_status=asset["status"],
            ), 409

        connection.execute(
            f"""
            INSERT INTO {ASSIGNMENTS} (asset_id, user_id, request_id, assigned_by)
            VALUES (%s, %s, %s, %s)
            """,
            (asset_id, found["requested_by"], request_id, session["user_id"]),
        )
        connection.execute(
            f"UPDATE {ASSETS} SET status = 'assigned' WHERE asset_id = %s",
            (asset_id,),
        )
        connection.execute(
            f"""
            UPDATE {REQUESTS}
            SET status = 'fulfilled', asset_id = %s, fulfilled_by = %s, updated_at = NOW()
            WHERE request_id = %s
            """,
            (asset_id, session["user_id"], request_id),
        )
        record_event(
            connection, "request", request_id, "fulfilled",
            f"Issued: {asset['name']}.", session["user_id"],
        )
        # TODO: notify the requester once notifications exist.
        row = connection.execute(
            f"{REQUEST_SELECT} WHERE r.request_id = %s", (request_id,)
        ).fetchone()
        attach_history(connection, "request", [row], "request_id")

    return jsonify(request=row), 200
