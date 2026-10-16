"""Admin-only user account management and activity API."""

from flask import Blueprint, jsonify, request, session

from ..admin_accounts import (
    create_account,
    deactivate_account,
    get_account,
    list_accounts,
    update_account,
)
from ..auth import roles_required
from ..db import connect_database
from ..services.audit import AuditSchemaNotConfigured, get_account_activity


users_bp = Blueprint("users", __name__)


def _payload():
    data = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    return data if isinstance(data, dict) else {}


@users_bp.get("/assignable")
@roles_required("store_manager")
def assignable_users():
    """List active users for the store manager's asset assignment form."""
    with connect_database() as connection:
        users = connection.execute(
            '''SELECT user_id, username, role FROM "Users"
               WHERE is_active = TRUE ORDER BY username'''
        ).fetchall()
    return jsonify(users=users), 200


@users_bp.get("/accounts")
@roles_required("admin")
def accounts_list():
    try:
        accounts = list_accounts(session["user_id"])
    except PermissionError as error:
        return jsonify(error=str(error)), 403
    return jsonify(accounts=accounts), 200


@users_bp.get("/accounts/<int:user_id>")
@roles_required("admin")
def accounts_get(user_id):
    try:
        account = get_account(session["user_id"], user_id)
    except PermissionError as error:
        return jsonify(error=str(error)), 403
    if account is None:
        return jsonify(error="Account not found."), 404
    return jsonify(account=account), 200


@users_bp.post("/accounts")
@roles_required("admin")
def accounts_create():
    data = _payload()
    try:
        account = create_account(
            session["user_id"],
            data.get("username"),
            data.get("email"),
            data.get("password"),
            data.get("role"),
        )
    except PermissionError as error:
        return jsonify(error=str(error)), 403
    except ValueError as error:
        return jsonify(error=str(error)), 400
    return jsonify(account=account), 201


@users_bp.patch("/accounts/<int:user_id>")
@roles_required("admin")
def accounts_update(user_id):
    try:
        account = update_account(session["user_id"], user_id, _payload())
    except PermissionError as error:
        return jsonify(error=str(error)), 403
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if account is None:
        return jsonify(error="Account not found."), 404
    return jsonify(account=account), 200


@users_bp.delete("/accounts/<int:user_id>")
@roles_required("admin")
def accounts_delete(user_id):
    try:
        account = deactivate_account(session["user_id"], user_id)
    except PermissionError as error:
        return jsonify(error=str(error)), 403
    except ValueError as error:
        return jsonify(error=str(error)), 409
    if account is None:
        return jsonify(error="Account not found."), 404
    return jsonify(account=account), 200


@users_bp.get("/accounts/activity")
@roles_required("admin")
def account_activity():
    """List other user accounts, their status, and last login time."""
    try:
        accounts = get_account_activity(session["user_id"])
    except AuditSchemaNotConfigured as error:
        return jsonify(error=str(error)), 503

    return jsonify(accounts=accounts), 200