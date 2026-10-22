import re
from decimal import Decimal, InvalidOperation

from ..db import connect_database
from ..integrations.daraja_b2c import (
    DarajaConfig,
    DarajaRejected,
    DarajaSubmissionUncertain,
    get_access_token,
    submit_b2c,
)
from .audit import record_audit, record_payment_history


def _approved_disbursement(connection, disbursement_id, user_id):
    approval = connection.execute(
        '''SELECT approval_id, requested_by, decided_by
           FROM "Approval_Items"
           WHERE request_type = 'disbursement'
             AND reference_id = %s
             AND status = 'approved'
           ORDER BY decided_at DESC, approval_id DESC
           LIMIT 1
           FOR UPDATE''',
        (disbursement_id,),
    ).fetchone()
    if approval is None:
        raise ValueError("This payout must be approved before it can be sent.")
    if approval["decided_by"] == approval["requested_by"]:
        raise ValueError("The requester cannot approve their own payout.")
    if approval["decided_by"] == user_id:
        raise ValueError("A different authorized user must submit the approved payout.")


def submit_disbursement(disbursement_id, *, user_id):
    """Submit one approved payout to Daraja sandbox; final status comes by callback."""
    config = DarajaConfig.from_env()
    access_token = get_access_token(config)

    with connect_database() as connection:
        row = connection.execute(
            '''SELECT * FROM "Disbursements"
               WHERE disbursement_id = %s FOR UPDATE''',
            (disbursement_id,),
        ).fetchone()
        if row is None:
            raise LookupError("Disbursement not found.")
        if row["status"] != "pending":
            raise ValueError(
                f"Only pending payouts can be sent. Current status: {row['status']}."
            )
        if row["provider"] != "daraja_b2c_sandbox":
            raise ValueError("This payout is not configured for the Daraja sandbox.")
        if row["currency"] != "KES":
            raise ValueError("Daraja B2C sandbox payouts must use KES.")
        amount = Decimal(str(row["amount"]))
        if (
            not amount.is_finite()
            or amount <= 0
            or amount != amount.to_integral_value()
            or amount > Decimal("70000")
        ):
            raise ValueError("Payout amount must be whole KES from 1 to 70,000.")
        if not isinstance(row["recipient_phone"], str) or not re.fullmatch(
            r"254[17]\d{8}", row["recipient_phone"]
        ):
            raise ValueError("Payout has no valid Kenyan mobile number.")
        _approved_disbursement(connection, disbursement_id, user_id)

        connection.execute(
            '''UPDATE "Disbursements"
               SET status = 'processing', submitted_by = %s,
                   provider_status_message = 'Submitting to Daraja sandbox.',
                   updated_at = NOW()
               WHERE disbursement_id = %s''',
            (user_id, disbursement_id),
        )

    try:
        result = submit_b2c(
            config,
            access_token,
            amount=amount,
            phone_number=row["recipient_phone"],
            reference=row["reference"],
            occasion=row["description"] or row["reference"],
        )
    except DarajaRejected as error:
        message = str(error)[:500]
        with connect_database() as connection:
            updated = connection.execute(
                '''UPDATE "Disbursements"
                   SET status = 'failed', failure_reason = %s,
                       provider_status_message = %s, updated_at = NOW()
                   WHERE disbursement_id = %s AND status = 'processing'
                   RETURNING *''',
                (message, message, disbursement_id),
            ).fetchone()
            if updated is not None:
                record_payment_history(updated, message, connection=connection)
                record_audit(
                    disbursement_id,
                    "payout_failed",
                    message,
                    user_id=user_id,
                    connection=connection,
                )
        return dict(updated), {"status": "failed", "message": message}
    except DarajaSubmissionUncertain as error:
        message = str(error)[:500]
        with connect_database() as connection:
            updated = connection.execute(
                '''UPDATE "Disbursements"
                   SET provider_status_message = %s, updated_at = NOW()
                   WHERE disbursement_id = %s AND status = 'processing'
                   RETURNING *''',
                (message, disbursement_id),
            ).fetchone()
            if updated is not None:
                record_payment_history(updated, message, connection=connection)
                record_audit(
                    disbursement_id,
                    "payout_needs_reconciliation",
                    message,
                    user_id=user_id,
                    connection=connection,
                )
        return dict(updated), {
            "status": "processing",
            "message": message,
            "needs_reconciliation": True,
        }

    with connect_database() as connection:
        updated = connection.execute(
            '''UPDATE "Disbursements"
               SET daraja_conversation_id = %s,
                   daraja_originator_conversation_id = %s,
                   provider_status_message = %s,
                   updated_at = NOW()
               WHERE disbursement_id = %s AND status = 'processing'
               RETURNING *''',
            (
                result["conversation_id"],
                result["originator_conversation_id"],
                result["message"],
                disbursement_id,
            ),
        ).fetchone()
        if updated is None:
            raise RuntimeError(
                "Daraja accepted the payout, but its tracking record could not be "
                "updated. Reconcile the transaction before taking further action."
            )
        record_payment_history(updated, result["message"], connection=connection)
        record_audit(
            disbursement_id,
            "payout_submitted_to_daraja_sandbox",
            result["message"],
            user_id=user_id,
            connection=connection,
        )
    return dict(updated), {
        "status": "processing",
        "message": "Payout submitted to Daraja sandbox; awaiting callback.",
    }


def _result_parameters(result):
    parameters = result.get("ResultParameters")
    if not isinstance(parameters, dict):
        return {}
    entries = parameters.get("ResultParameter")
    if not isinstance(entries, list):
        return {}
    return {
        entry.get("Key"): entry.get("Value")
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("Key"), str)
    }


def complete_daraja_result(payload):
    """Apply one token-authorized, correlated Daraja result callback idempotently."""
    result = payload.get("Result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ValueError("Callback must contain a Result object.")
    conversation_id = result.get("ConversationID")
    originator_id = result.get("OriginatorConversationID")
    result_code = result.get("ResultCode")
    if (
        not conversation_id
        or not originator_id
        or result_code is None
        or isinstance(result_code, bool)
    ):
        raise ValueError("Callback is missing transaction correlation fields.")
    if isinstance(result_code, int):
        result_code = int(result_code)
    elif isinstance(result_code, str) and re.fullmatch(r"-?\d+", result_code):
        result_code = int(result_code)
    else:
        result_code = None
    if result_code is None:
        raise ValueError("Callback ResultCode must be an integer.")

    parameters = _result_parameters(result)
    is_success = result_code == 0
    transaction_receipt = parameters.get("TransactionReceipt")
    received_amount = parameters.get(
        "TransactionAmount", parameters.get("Amount")
    )
    description = str(result.get("ResultDesc") or "Daraja callback received.")[:500]

    with connect_database() as connection:
        row = connection.execute(
            '''SELECT * FROM "Disbursements"
               WHERE daraja_conversation_id = %s
                 AND daraja_originator_conversation_id = %s
               FOR UPDATE''',
            (str(conversation_id), str(originator_id)),
        ).fetchone()
        if row is None:
            return "not_found"
        if row["status"] != "processing":
            return "duplicate"

        if is_success:
            try:
                callback_amount = Decimal(str(received_amount))
                expected_amount = Decimal(str(row["amount"]))
            except (InvalidOperation, TypeError, ValueError):
                callback_amount = None
                expected_amount = None
            if (
                not transaction_receipt
                or callback_amount is None
                or expected_amount is None
                or not callback_amount.is_finite()
                or not expected_amount.is_finite()
                or callback_amount != expected_amount
            ):
                message = (
                    "Daraja reported success, but the receipt or amount did not "
                    "match. Manual reconciliation is required."
                )
                connection.execute(
                    '''UPDATE "Disbursements"
                       SET provider_status_message = %s, updated_at = NOW()
                       WHERE disbursement_id = %s''',
                    (message, row["disbursement_id"]),
                )
                record_audit(
                    row["disbursement_id"],
                    "payout_callback_requires_reconciliation",
                    message,
                    user_id=row["submitted_by"],
                    connection=connection,
                )
                return "reconcile"

            updated = connection.execute(
                '''UPDATE "Disbursements"
                   SET status = 'paid', payment_reference = %s, receipt_ref = %s,
                       daraja_transaction_id = %s, paid_by = submitted_by, paid_at = NOW(),
                       failure_reason = NULL, provider_status_message = %s,
                       updated_at = NOW()
                   WHERE disbursement_id = %s AND status = 'processing'
                   RETURNING *''',
                (
                    str(transaction_receipt)[:100],
                    str(transaction_receipt)[:100],
                    str(transaction_receipt)[:100],
                    description,
                    row["disbursement_id"],
                ),
            ).fetchone()
            record_payment_history(updated, description, connection=connection)
            record_audit(
                row["disbursement_id"],
                "payout_paid",
                description,
                user_id=row["submitted_by"],
                connection=connection,
            )
            return "processed"

        updated = connection.execute(
            '''UPDATE "Disbursements"
               SET status = 'failed', failure_reason = %s,
                   provider_status_message = %s, updated_at = NOW()
               WHERE disbursement_id = %s AND status = 'processing'
               RETURNING *''',
            (description, description, row["disbursement_id"]),
        ).fetchone()
        record_payment_history(updated, description, connection=connection)
        record_audit(
            row["disbursement_id"],
            "payout_failed",
            description,
            user_id=row["submitted_by"],
            connection=connection,
        )
        return "processed"


def record_daraja_timeout(payload):
    """Record a timeout notice without treating an ambiguous payout as failed."""
    result = payload.get("Result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ValueError("Callback must contain a Result object.")
    conversation_id = result.get("ConversationID")
    originator_id = result.get("OriginatorConversationID")
    if not conversation_id or not originator_id:
        raise ValueError("Callback is missing transaction correlation fields.")

    message = str(
        result.get("ResultDesc")
        or "Daraja timeout notice received; payout remains under reconciliation."
    )[:500]
    with connect_database() as connection:
        row = connection.execute(
            '''SELECT * FROM "Disbursements"
               WHERE daraja_conversation_id = %s
                 AND daraja_originator_conversation_id = %s
               FOR UPDATE''',
            (str(conversation_id), str(originator_id)),
        ).fetchone()
        if row is None:
            return "not_found"
        if row["status"] != "processing":
            return "duplicate"
        if row["provider_status_message"] == message:
            return "duplicate"
        connection.execute(
            '''UPDATE "Disbursements"
               SET provider_status_message = %s, updated_at = NOW()
               WHERE disbursement_id = %s''',
            (message, row["disbursement_id"]),
        )
        record_audit(
            row["disbursement_id"],
            "payout_timeout_notice",
            message,
            user_id=row["submitted_by"],
            connection=connection,
        )
    return "reconcile"
