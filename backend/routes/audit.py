"""Role-protected company audit API."""

from flask import Blueprint, jsonify, session

from ..auth import roles_required
from ..services.audit import (
    AuditSchemaNotConfigured,
    get_disbursement_audit,
    get_procurement_audit,
    get_project_audit,
)


audit_bp = Blueprint("audit", __name__)
AUDIT_ROLES = ("admin", "manager")
PROCUREMENT_ROLES = (*AUDIT_ROLES, "store_manager")


def _schema_not_configured(error):
    return jsonify(error=str(error)), 503


@audit_bp.get("/company")
@roles_required(*PROCUREMENT_ROLES)
def company_audit():
    """Return card data for the company audit dashboard.

    Store managers receive procurement data only. Admins and managers receive
    project, disbursement, and procurement cards.
    """
    role = session["role"]
    try:
        if role == "store_manager":
            cards = {"procurement": get_procurement_audit()}
        else:
            cards = {
                "projects": get_project_audit(),
                "disbursements": get_disbursement_audit(),
                "procurement": get_procurement_audit(),
            }
    except AuditSchemaNotConfigured as error:
        return _schema_not_configured(error)

    return jsonify(cards=cards), 200


@audit_bp.get("/company/projects")
@roles_required(*AUDIT_ROLES)
def project_audit():
    try:
        return jsonify(projects=get_project_audit()), 200
    except AuditSchemaNotConfigured as error:
        return _schema_not_configured(error)


@audit_bp.get("/company/disbursements")
@roles_required(*AUDIT_ROLES)
def disbursement_audit():
    try:
        return jsonify(disbursements=get_disbursement_audit()), 200
    except AuditSchemaNotConfigured as error:
        return _schema_not_configured(error)


@audit_bp.get("/company/procurement")
@roles_required(*PROCUREMENT_ROLES)
def procurement_audit():
    try:
        return jsonify(procurement=get_procurement_audit()), 200
    except AuditSchemaNotConfigured as error:
        return _schema_not_configured(error)