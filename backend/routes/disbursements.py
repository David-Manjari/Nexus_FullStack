import uuid
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request, session

from ..auth import roles_required
from ..db import connect_database
from ..services.audit import (
    get_audit_history,
    get_payment_history,
    record_audit,
)
from ..services.disbursements import process_disbursement

disbursements_bp = Blueprint(
    "disbursements",
    __name__,
    url_prefix="/api",
)

VALID_STATUSES = {"pending", "processing", "success", "paid", "failed"}
READ_ROLES = ("admin", "manager")
WRITE_ROLES = ("admin", "manager")
MAX_AMOUNT = Decimal("9999999999.99")


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


@disbursements_bp.get("/disbursements")
@roles_required(*READ_ROLES)
def list_disbursements():
    status = request.args.get("status")
    if status and status not in VALID_STATUSES:
        return jsonify(error="Invalid payout status."), 400

    query = 'SELECT * FROM "Disbursements"'
    params = ()
    if status:
        query += " WHERE status = %s"
        params = (status,)
    query += " ORDER BY created_at DESC, disbursement_id DESC"

    with connect_database() as connection:
        rows = connection.execute(query, params).fetchall()
    return jsonify([dict(row) for row in rows]), 200


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
    description = data.get("description", "")
    currency = data.get("currency", "KES")
    amount = _amount(data.get("amount"))

    if not isinstance(payee, str) or not payee.strip():
        return jsonify(error="A payee name is required."), 400

    if not isinstance(description, str):
        return jsonify(error="Description must be text."), 400

    if not isinstance(currency, str) or not currency.strip():
        return jsonify(error="A currency is required."), 400

    if amount is None:
        return jsonify(error="Amount must be a finite positive number."), 400

    reference = "NEX-" + uuid.uuid4().hex[:10].upper()
    with connect_database() as connection:
        row = connection.execute(
            '''INSERT INTO "Disbursements"
                   (reference, payee, amount, currency, description)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING *''',
            (reference, payee.strip(), amount, currency.strip().upper(), description.strip()),
        ).fetchone()
        record_audit(
            row["disbursement_id"],
            "payout_created",
            f"Payout created for {payee.strip()}.",
            user_id=session["user_id"],
            connection=connection,
        )
    return jsonify(dict(row)), 201


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
    return jsonify(dict(row)), 200


@disbursements_bp.post("/disbursements/<int:disbursement_id>/process")
@roles_required(*WRITE_ROLES)
def process_payout(disbursement_id):
    data = _payload()
    simulated_result = data.get("simulated_result", "paid")

    if simulated_result not in ("paid", "failed"):
        return jsonify(
            error="simulated_result must be 'paid' or 'failed'."
        ), 400

    try:
        payout, result = process_disbursement(
            disbursement_id,
            simulated_result,
            user_id=session["user_id"],
        )
        return jsonify(
            disbursement=payout,
            payment=result,
        ), 200
    except LookupError as error:
        return jsonify(error=str(error)), 404
    except ValueError as error:
        return jsonify(error=str(error)), 409


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
