import uuid
import hmac
import os
import re
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request, session

from ..auth import roles_required
from ..db import connect_database
from ..integrations.daraja_b2c import DarajaConfigurationError
from ..services.approvals import create_approval
from ..services.audit import (
    get_audit_history,
    get_payment_history,
    record_audit,
)
from ..services.disbursements import (
    complete_daraja_result,
    record_daraja_timeout,
    submit_disbursement,
)

disbursements_bp = Blueprint(
    "disbursements",
    __name__,
    url_prefix="/api",
)

VALID_STATUSES = {"pending", "processing", "success", "paid", "failed"}
READ_ROLES = ("admin", "manager")
WRITE_ROLES = ("admin", "manager")
MAX_AMOUNT = Decimal("9999999999.99")
MAX_B2C_AMOUNT = Decimal("70000")


def _payload():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _amount(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0 or amount > MAX_AMOUNT:
        return None
    return amount.quantize(Decimal("0.01"))


def _kenyan_phone(value):
    if not isinstance(value, str):
        return None
    digits = re.sub(r"[\s()-]", "", value.strip())
    if digits.startswith("+"):
        digits = digits[1:]
    if digits.startswith("0") and len(digits) == 10:
        digits = "254" + digits[1:]
    if re.fullmatch(r"254[17]\d{8}", digits):
        return digits
    return None


def _public_disbursement(row):
    result = dict(row)
    phone = result.get("recipient_phone")
    if phone:
        result["recipient_phone"] = f"****{phone[-4:]}"
    return result


def _callback_is_authorized(token):
    configured = os.environ.get("DARAJA_CALLBACK_TOKEN", "")
    enabled = os.environ.get("DARAJA_B2C_ENABLED", "").lower() == "true"
    return (
        enabled
        and len(configured) >= 32
        and hmac.compare_digest(configured, token)
    )


@disbursements_bp.get("/disbursements")
@roles_required(*READ_ROLES)
def list_disbursements():
    status = request.args.get("status")
    if status and status not in VALID_STATUSES:
        return jsonify(error="Invalid payout status."), 422

    query = 'SELECT * FROM "Disbursements"'
    params = ()
    if status:
        query += " WHERE status = %s"
        params = (status,)
    query += " ORDER BY created_at DESC, disbursement_id DESC"

    with connect_database() as connection:
        rows = connection.execute(query, params).fetchall()
    return jsonify([_public_disbursement(row) for row in rows]), 200


@disbursements_bp.get("/disbursements/summary")
@roles_required(*READ_ROLES)
def disbursement_summary():
    with connect_database() as connection:
        rows = connection.execute(
            '''SELECT status, COUNT(*) AS count,
                      COALESCE(SUM(amount), 0) AS total
               FROM "Disbursements"
               GROUP BY status'''
        ).fetchall()

    summary = {status: {"count": 0, "total": 0} for status in VALID_STATUSES}
    for row in rows:
        summary[row["status"]] = {"count": row["count"], "total": row["total"]}
    return jsonify(summary), 200


@disbursements_bp.post("/disbursements")
@roles_required(*WRITE_ROLES)
def create_disbursement():
    data = _payload()

    payee = data.get("payee")
    phone = _kenyan_phone(data.get("recipient_phone"))
    description = data.get("description", "")
    currency = data.get("currency", "KES")
    amount = _amount(data.get("amount"))

    if not isinstance(payee, str) or not payee.strip():
        return jsonify(error="A payee name is required."), 422
    if len(payee.strip()) > 200:
        return jsonify(error="Payee name is too long."), 422
    if phone is None:
        return jsonify(
            error="A valid Kenyan mobile number is required (07..., 01..., or 254...)."
        ), 422

    if not isinstance(description, str):
        return jsonify(error="Description must be text."), 422
    if len(description) > 500:
        return jsonify(error="Description must be 500 characters or fewer."), 422

    if not isinstance(currency, str) or currency.strip().upper() != "KES":
        return jsonify(error="Daraja B2C sandbox payouts must use KES."), 422

    if amount is None:
        return jsonify(error="Amount must be a finite positive number."), 422
    if amount != amount.to_integral_value():
        return jsonify(error="Daraja B2C payout amounts must be whole KES."), 422
    if amount > MAX_B2C_AMOUNT:
        return jsonify(error="Sandbox payout amount cannot exceed KES 70,000."), 422

    reference = "NEX-" + uuid.uuid4().hex[:10].upper()
    with connect_database() as connection:
        row = connection.execute(
            '''INSERT INTO "Disbursements"
                   (reference, payee, recipient_phone, amount, currency,
                    description, provider)
               VALUES (%s, %s, %s, %s, 'KES', %s, 'daraja_b2c_sandbox')
               RETURNING *''',
            (reference, payee.strip(), phone, amount, description.strip()),
        ).fetchone()
        record_audit(
            row["disbursement_id"],
            "payout_created",
            f"Payout created for {payee.strip()}.",
            user_id=session["user_id"],
            connection=connection,
        )
        create_approval(
            connection,
            "disbursement",
            session["user_id"],
            f"Disbursement of {row['currency']} {row['amount']:,.2f} to {row['payee']} ({row['reference']})"[:500],
            reference_id=row["disbursement_id"],
        )
    return jsonify(_public_disbursement(row)), 201


@disbursements_bp.get("/disbursements/<int:disbursement_id>")
@roles_required(*READ_ROLES)
def get_disbursement(disbursement_id):
    with connect_database() as connection:
        row = connection.execute(
            'SELECT * FROM "Disbursements" WHERE disbursement_id = %s',
            (disbursement_id,),
        ).fetchone()
    if row is None:
        return jsonify(error="Disbursement not found."), 404
    return jsonify(_public_disbursement(row)), 200


@disbursements_bp.post("/disbursements/<int:disbursement_id>/process")
@roles_required(*WRITE_ROLES)
def process_payout(disbursement_id):
    try:
        payout, result = submit_disbursement(
            disbursement_id,
            user_id=session["user_id"],
        )
        response_code = 202 if payout["status"] == "processing" else 200
        return jsonify(
            disbursement=_public_disbursement(payout),
            payment=result,
        ), response_code
    except LookupError as error:
        return jsonify(error=str(error)), 404
    except ValueError as error:
        return jsonify(error=str(error)), 409
    except DarajaConfigurationError as error:
        return jsonify(error=str(error)), 503


@disbursements_bp.post("/daraja/b2c/result/<token>")
def daraja_b2c_result(token):
    if not _callback_is_authorized(token):
        return jsonify(error="Not found."), 404
    payload = request.get_json(silent=True)
    try:
        outcome = complete_daraja_result(payload)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if outcome == "not_found":
        return jsonify(error="Payout correlation was not found."), 404
    return jsonify(ResultCode=0, ResultDesc="Callback processed."), 200


@disbursements_bp.post("/daraja/b2c/timeout/<token>")
def daraja_b2c_timeout(token):
    if not _callback_is_authorized(token):
        return jsonify(error="Not found."), 404
    payload = request.get_json(silent=True)
    try:
        outcome = record_daraja_timeout(payload)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if outcome == "not_found":
        return jsonify(error="Payout correlation was not found."), 404
    return jsonify(ResultCode=0, ResultDesc="Timeout notice recorded."), 200


@disbursements_bp.get("/disbursements/<int:disbursement_id>/history")
@roles_required(*READ_ROLES)
def disbursement_history(disbursement_id):
    with connect_database() as connection:
        exists = connection.execute(
            'SELECT 1 FROM "Disbursements" WHERE disbursement_id = %s',
            (disbursement_id,),
        ).fetchone()
        if exists is None:
            return jsonify(error="Disbursement not found."), 404
        payments = get_payment_history(disbursement_id, connection=connection)
        audit = get_audit_history(disbursement_id, connection=connection)
    return jsonify(payments=payments, audit=audit), 200


@disbursements_bp.get("/payment-history")
@roles_required(*READ_ROLES)
def payment_history():
    with connect_database() as connection:
        rows = connection.execute(
            '''SELECT * FROM "Payment_History"
               ORDER BY created_at DESC, history_id DESC'''
        ).fetchall()
    return jsonify([dict(row) for row in rows]), 200