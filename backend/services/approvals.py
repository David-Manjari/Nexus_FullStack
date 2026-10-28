"""Approval rules and actions: who may see which request, and recording decisions.

Other modules (equipment assignment, procurement, escalations, disbursements)
call create_approval() inside their own transaction when they need a decision.
"""

from psycopg.types.json import Jsonb

from .notifications import create_notification

APPROVALS = '"Approval_Items"'
USERS = '"Users"'
VIEWS = '"Approval_Views"'

# Edit this list to match the leader's request types.
REQUEST_TYPES = (
    "equipment_assignment",
    "equipment_procurement",
    "tool_assignment",
    "escalation",
    "disbursement",
)

# Task T5: which roles see which request types.
#   admin, manager: everything except tool assignment
ROLE_VISIBILITY = {
    "admin": tuple(t for t in REQUEST_TYPES if t != "tool_assignment"),
    "manager": tuple(t for t in REQUEST_TYPES if t != "tool_assignment"),
}
APPROVER_ROLES = tuple(ROLE_VISIBILITY)


class AlreadyDecided(RuntimeError):
    """The request was approved or rejected before this decision arrived."""


def visible_types(role):
    return ROLE_VISIBILITY.get(role, ())


def _audit(connection, user_id, action, approval_id, details):
    connection.execute(
        'INSERT INTO "Audit_Log" (user_id, action, entity_type, entity_id, details) '
        "VALUES (%s, %s, 'approval', %s, %s)",
        (user_id, action, approval_id, Jsonb(details)),
    )


def create_approval(connection, request_type, requested_by, summary, reference_id=None):
    """Open a pending approval. Call this from the module that raised the request."""
    if request_type not in REQUEST_TYPES:
        raise ValueError(f"request_type must be one of: {', '.join(REQUEST_TYPES)}.")
    summary = summary.strip() if isinstance(summary, str) else ""
    if not summary:
        raise ValueError("A summary is required.")

    approval = connection.execute(
        f"""INSERT INTO {APPROVALS} (request_type, reference_id, summary, requested_by)
            VALUES (%s, %s, %s, %s) RETURNING *""",
        (request_type, reference_id, summary, requested_by),
    ).fetchone()
    _audit(
        connection, requested_by, "approval_requested", approval["approval_id"],
        {"request_type": request_type, "reference_id": reference_id},
    )
    return approval


def list_pending(connection, role):
    """Task T6: only the pending approvals this role is allowed to see."""
    types = list(visible_types(role))
    if not types:
        return []
    rows = connection.execute(
        f"""SELECT a.approval_id, a.request_type, a.reference_id, a.summary,
                   a.requested_by, u.username AS requested_by_name, a.created_at
            FROM {APPROVALS} a
            JOIN {USERS} u ON u.user_id = a.requested_by
            WHERE a.status = 'pending' AND a.request_type = ANY(%s)
            ORDER BY a.created_at, a.approval_id""",
        (types,),
    ).fetchall()
    return [dict(row) for row in rows]


def decide(connection, approval_id, user_id, role, decision, reason=None):
    """Tasks T7 and T17: approve or reject. A reason is required to reject.

    Raises ValueError (validation), LookupError (unknown id),
    PermissionError (role may not decide this type) or AlreadyDecided.
    """
    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be 'approved' or 'rejected'.")
    reason = reason.strip() if isinstance(reason, str) else None
    if decision == "rejected" and not reason:
        raise ValueError("A reason is required when rejecting a request.")

    approval = connection.execute(
        f"SELECT * FROM {APPROVALS} WHERE approval_id = %s FOR UPDATE", (approval_id,)
    ).fetchone()
    if approval is None:
        raise LookupError("Approval not found.")
    if approval["request_type"] not in visible_types(role):
        raise PermissionError("Your role cannot decide this type of request.")
    if approval["status"] != "pending":
        raise AlreadyDecided(f"This request was already {approval['status']}.")

    updated = connection.execute(
        f"""UPDATE {APPROVALS}
            SET status = %s, decided_by = %s, decision_reason = %s, decided_at = NOW()
            WHERE approval_id = %s RETURNING *""",
        (decision, user_id, reason, approval_id),
    ).fetchone()
    _audit(
        connection, user_id, f"approval_{decision}", approval_id,
        {
            "request_type": approval["request_type"],
            "reference_id": approval["reference_id"],
            "reason": reason,
        },
    )
    _after_decision(connection, updated)
    return updated


def _after_decision(connection, approval):
    """Notify the requester when an approval is approved or rejected."""
    if approval["request_type"] == "equipment_procurement":
        _update_procurement_status(connection, approval)

    request_type = approval["request_type"].replace("_", " ")
    reference_id = approval["reference_id"]
    reference = f" #{reference_id}" if reference_id is not None else ""
    message = f"Your {request_type} request{reference} was {approval['status']}."
    reason = approval["decision_reason"]
    if reason:
        message += f" Reason: {reason}"
    create_notification(
        connection,
        approval["requested_by"],
        message,
        "approval_decision",
    )


def _update_procurement_status(connection, approval):
    from .request_workflow import log_action, record_event

    procurement_id = approval["reference_id"]
    procurement = connection.execute(
        '''SELECT status FROM "Procurements"
           WHERE procurement_id = %s
           FOR UPDATE''',
        (procurement_id,),
    ).fetchone()
    if procurement is None:
        raise LookupError("Procurement not found.")
    if procurement["status"] != "pending_approval":
        raise AlreadyDecided("This procurement is no longer awaiting approval.")

    status = approval["status"]
    connection.execute(
        '''UPDATE "Procurements"
           SET status = %s, updated_at = NOW()
           WHERE procurement_id = %s''',
        (status, procurement_id),
    )
    note = (
        "Procurement approved. Create a disbursement request when ready."
        if status == "approved"
        else f"Procurement rejected. {approval['decision_reason']}"
    )
    record_event(
        connection, "procurement", procurement_id, status, note,
        approval["decided_by"],
    )
    log_action(
        connection, approval["decided_by"], f"procurement_{status}",
        "procurement", procurement_id,
        {"approval_id": approval["approval_id"], "reason": approval["decision_reason"]},
    )


def record_view(connection, user_id):
    """Task T8: remember that this user has opened the pending approvals list."""
    connection.execute(
        f"""INSERT INTO {VIEWS} (user_id, viewed_at) VALUES (%s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET viewed_at = NOW()""",
        (user_id,),
    )


def has_viewed_pending(connection, user_id):
    """Record that a manager has reviewed the pending approvals list."""
    row = connection.execute(
        f"SELECT 1 AS seen FROM {VIEWS} WHERE user_id = %s", (user_id,)
    ).fetchone()
    return row is not None