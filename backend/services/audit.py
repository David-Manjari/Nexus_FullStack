"""Audit queries: dashboard summaries, account activity and disbursement audit trail."""

from contextlib import contextmanager

from psycopg.types.json import Jsonb

from ..db import connect_database


class AuditSchemaNotConfigured(RuntimeError):
	"""Raised when an audit dashboard's backing tables are not provisioned."""


@contextmanager
def _use(connection=None):
	"""Reuse the caller's connection (and transaction) or open a new one."""
	if connection is not None:
		yield connection
	else:
		with connect_database() as new_connection:
			yield new_connection


def _all(connection, query, params=()):
	return [dict(row) for row in connection.execute(query, params).fetchall()]

def get_project_audit():
	with _use() as connection:
		return _all(
			connection,
			'''SELECT status, COUNT(*) AS project_count
			   FROM "Projects"
			   GROUP BY status
			   ORDER BY status''',
		)


def get_project_status_history(project_id, limit=100):
	with _use() as connection:
		return _all(
			connection,
			'''SELECT h.history_id, h.from_status, h.to_status, h.reason,
			          h.changed_at, h.changed_by, u.username AS changed_by_name
			   FROM "Project_Status_History" h
			   JOIN "Users" u ON u.user_id = h.changed_by
			   WHERE h.project_id = %s
			   ORDER BY h.changed_at DESC, h.history_id DESC
			   LIMIT %s''',
			(project_id, limit),
		)

  
def get_account_activity(user_id, limit=50):
	with _use() as connection:
		profile = connection.execute(
			'''SELECT user_id, username, email, role, is_active, last_login_at, created_at
			   FROM "Users" WHERE user_id = %s''',
			(user_id,),
		).fetchone()
		if profile is None:
			return None

		events = _all(
			connection,
			'''SELECT audit_id, action, entity_type, entity_id, details, created_at
			   FROM "Audit_Log"
			   WHERE user_id = %s
			   ORDER BY created_at DESC, audit_id DESC
			   LIMIT %s''',
			(user_id, limit),
		)
		requests_by_status = _all(
			connection,
			'''SELECT status, COUNT(*) AS request_count
			   FROM "Requests" WHERE requester_id = %s
			   GROUP BY status ORDER BY status''',
			(user_id,),
		)
		procurements_by_status = _all(
			connection,
			'''SELECT status, COUNT(*) AS procurement_count
			   FROM "Procurements" WHERE requested_by = %s
			   GROUP BY status ORDER BY status''',
			(user_id,),
		)
		decisions = _all(
			connection,
			'''SELECT 'procurement' AS kind, procurement_id AS entity_id,
			          level AS step, decision, decided_at
			   FROM "Approvals"
			   WHERE approver_id = %s AND decision <> 'pending'
			   UNION ALL
			   SELECT 'project', project_id, step_order, status, decided_at
			   FROM "Approval_Requests"
			   WHERE approver_id = %s AND status IN ('approved', 'rejected', 'skipped')
			   ORDER BY decided_at DESC NULLS LAST
			   LIMIT %s''',
			(user_id, user_id, limit),
		)
		unread = connection.execute(
			'''SELECT COUNT(*) AS unread FROM "Notifications"
			   WHERE user_id = %s AND is_read = FALSE''',
			(user_id,),
		).fetchone()["unread"]

	return {
		"user": dict(profile),
		"recent_events": events,
		"requests_by_status": requests_by_status,
		"procurements_by_status": procurements_by_status,
		"recent_decisions": decisions,
		"unread_notifications": unread,
	}

def get_procurement_audit(limit=50):
	with _use() as connection:
		by_status = _all(
			connection,
			'''SELECT status,
			          COUNT(*) AS procurement_count,
			          COALESCE(SUM(estimated_cost), 0) AS total_estimated_cost
			   FROM "Procurements"
			   GROUP BY status ORDER BY status''',
		)
		pending_approvals = _all(
			connection,
			'''SELECT p.procurement_id, p.item_name, p.estimated_cost,
			          p.status AS procurement_status, a.level, a.approver_id, a.created_at
			   FROM "Approvals" a
			   JOIN "Procurements" p ON p.procurement_id = a.procurement_id
			   WHERE a.decision = 'pending'
			   ORDER BY a.created_at
			   LIMIT %s''',
			(limit,),
		)
		approved_unpaid = _all(
			connection,
			'''SELECT p.procurement_id, p.item_name, p.estimated_cost,
			          d.disbursement_id, d.status AS disbursement_status
			   FROM "Procurements" p
			   LEFT JOIN "Disbursements" d ON d.procurement_id = p.procurement_id
			   WHERE p.status = 'approved'
			     AND (d.disbursement_id IS NULL OR d.status NOT IN ('success', 'paid'))
			   ORDER BY p.created_at
			   LIMIT %s''',
			(limit,),
		)
		recent_decisions = _all(
			connection,
			'''SELECT a.procurement_id, p.item_name, a.level, a.decision, a.comment,
			          a.approver_id, u.username AS approver_name, a.decided_at
			   FROM "Approvals" a
			   JOIN "Procurements" p ON p.procurement_id = a.procurement_id
			   LEFT JOIN "Users" u ON u.user_id = a.approver_id
			   WHERE a.decision <> 'pending'
			   ORDER BY a.decided_at DESC NULLS LAST
			   LIMIT %s''',
			(limit,),
		)
	return {
		"by_status": by_status,
		"pending_approvals": pending_approvals,
		"approved_unpaid": approved_unpaid,
		"recent_decisions": recent_decisions,
	}

def record_audit(disbursement_id, action, details="", *, user_id=None, connection=None):
	with _use(connection) as conn:
		conn.execute(
			'''INSERT INTO "Disbursement_Audit_Logs" (disbursement_id, action, details)
			   VALUES (%s, %s, %s)''',
			(disbursement_id, action, details),
		)
		conn.execute(
			'''INSERT INTO "Audit_Log" (user_id, action, entity_type, entity_id, details)
			   VALUES (%s, %s, 'disbursement', %s, %s)''',
			(user_id, action, disbursement_id, Jsonb({"message": details})),
		)


def get_audit_history(disbursement_id, connection=None):
	"""Audit trail for one disbursement, newest first."""
	with _use(connection) as conn:
		return _all(
			conn,
			'''SELECT * FROM "Disbursement_Audit_Logs"
			   WHERE disbursement_id = %s
			   ORDER BY created_at DESC, log_id DESC''',
			(disbursement_id,),
		)


def record_payment_history(disbursement, message="", *, connection=None):
	with _use(connection) as conn:
		return conn.execute(
			'''INSERT INTO "Payment_History"
			       (disbursement_id, reference, payment_reference,
			        amount, currency, status, message)
			   VALUES (%s, %s, %s, %s, %s, %s, %s)
			   RETURNING *''',
			(
				disbursement["disbursement_id"],
				disbursement.get("reference"),
				disbursement.get("payment_reference"),
				disbursement["amount"],
				disbursement["currency"],
				disbursement["status"],
				message,
			),
		).fetchone()


def get_payment_history(disbursement_id, connection=None):
	with _use(connection) as conn:
		return _all(
			conn,
			'''SELECT * FROM "Payment_History"
			   WHERE disbursement_id = %s
			   ORDER BY created_at, history_id''',
			(disbursement_id,),
		)


def get_disbursement_audit(limit=50):
	"""Totals by status, failed payments and the latest audit events."""
	with _use() as connection:
		by_status = _all(
			connection,
			'''SELECT status,
			          COUNT(*) AS disbursement_count,
			          COALESCE(SUM(amount), 0) AS total_amount
			   FROM "Disbursements"
			   GROUP BY status ORDER BY status''',
		)
		failed = _all(
			connection,
			'''SELECT disbursement_id, reference, payee, amount, currency,
			          failure_reason, updated_at
			   FROM "Disbursements"
			   WHERE status = 'failed'
			   ORDER BY updated_at DESC
			   LIMIT %s''',
			(limit,),
		)
		recent_events = _all(
			connection,
			'''SELECT l.log_id, l.disbursement_id, d.reference, l.action,
			          l.details, l.created_at
			   FROM "Disbursement_Audit_Logs" l
			   LEFT JOIN "Disbursements" d ON d.disbursement_id = l.disbursement_id
			   ORDER BY l.created_at DESC, l.log_id DESC
			   LIMIT %s''',
			(limit,),
		)
	return {"by_status": by_status, "failed": failed, "recent_events": recent_events}
