from ..db import connect_database
from ..integrations.payment_client import simulate_payment
from .audit import record_audit, record_payment_history


def process_disbursement(disbursement_id, simulated_result="paid", user_id=None):
	# Step 1: lock the row, check it is pending, mark it processing, commit.
	with connect_database() as connection:
		row = connection.execute(
			'SELECT * FROM "Disbursements" WHERE disbursement_id = %s FOR UPDATE',
			(disbursement_id,),
		).fetchone()
		if row is None:
			raise LookupError("Disbursement not found.")
		if row["status"] != "pending":
			raise ValueError(
				f"Only pending payouts can be processed. "
				f"Current status: {row['status']}."
			)
		connection.execute(
			'''UPDATE "Disbursements"
			   SET status = 'processing', updated_at = NOW()
			   WHERE disbursement_id = %s''',
			(disbursement_id,),
		)

	# Step 2: call the payment provider outside any transaction or row lock.
	try:
		result = simulate_payment(row["amount"], row["currency"], simulated_result)
	except Exception as error:
		result = {
			"status": "failed",
			"payment_reference": None,
			"message": f"Payment provider error: {error}",
		}

	# Step 3: record the outcome, history and audit rows in one transaction.
	failure_reason = result["message"] if result["status"] == "failed" else None
	with connect_database() as connection:
		updated = connection.execute(
			'''UPDATE "Disbursements"
			   SET status = %s,
			       payment_reference = %s,
			       failure_reason = %s,
			       updated_at = NOW(),
			       paid_at = CASE WHEN %s::text IN ('paid', 'success')
			                      THEN NOW() ELSE NULL END
			   WHERE disbursement_id = %s
			   RETURNING *''',
			(
				result["status"],
				result["payment_reference"],
				failure_reason,
				result["status"],
				disbursement_id,
			),
		).fetchone()
		record_payment_history(updated, result["message"], connection=connection)
		record_audit(
			disbursement_id,
			"payout_" + result["status"],
			result["message"],
			user_id=user_id,
			connection=connection,
		)
	return dict(updated), result