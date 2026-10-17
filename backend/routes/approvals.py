"""Approval endpoints: list what is waiting for me, and approve or reject it.

Register in app.py:
    from .routes.approvals import approvals_bp
    app.register_blueprint(approvals_bp, url_prefix="/approvals")

Error codes: 401 not signed in, 403 wrong role, 404 not found,
409 already decided, 422 validation failed.
"""

from flask import Blueprint, jsonify, request, session

from ..auth import roles_required
from ..db import connect_database
from ..services.approvals import (
    APPROVER_ROLES,
    AlreadyDecided,
    decide,
    list_pending,
    record_view,
)

approvals_bp = Blueprint("approvals", __name__)


def _error(message, status):
    return jsonify(error=message), status


@approvals_bp.get("/pending")
@roles_required(*APPROVER_ROLES)
def pending_approvals():
    """Pending approvals for the signed-in user's role only."""
    with connect_database() as connection:
        approvals = list_pending(connection, session["role"])
        if session["role"] == "store_manager":
            record_view(connection, session["user_id"])
    return jsonify(approvals=approvals), 200


@approvals_bp.post("/<int:approval_id>/decision")
@roles_required(*APPROVER_ROLES)
def decide_approval(approval_id):
    """Body: {"decision": "approved" | "rejected", "reason": "..."}.

    A reason is required when rejecting.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return _error("Request body must be a JSON object.", 422)

    try:
        with connect_database() as connection:
            approval = decide(
                connection,
                approval_id,
                session["user_id"],
                session["role"],
                data.get("decision"),
                data.get("reason"),
            )
    except ValueError as error:
        return _error(str(error), 422)
    except LookupError as error:
        return _error(str(error), 404)
    except PermissionError as error:
        return _error(str(error), 403)
    except AlreadyDecided as error:
        return _error(str(error), 409)

    return jsonify(approval=dict(approval)), 200