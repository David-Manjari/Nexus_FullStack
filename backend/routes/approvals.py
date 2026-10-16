"""Sequential project approval inbox and decision routes."""

from flask import Blueprint, jsonify, request, session

from ..auth import roles_required
from ..services.workflow import WorkflowError, decide_approval, list_my_approvals


approvals_bp = Blueprint("approvals", __name__)
APPROVER_ROLES = ("admin", "manager")


@approvals_bp.get("/inbox")
@roles_required(*APPROVER_ROLES)
def approvals_inbox():
	try:
		approvals = list_my_approvals(session["user_id"])
	except WorkflowError as error:
		return jsonify(error=str(error)), error.status
	return jsonify(approvals=approvals), 200


@approvals_bp.post("/<int:approval_id>/decision")
@roles_required(*APPROVER_ROLES)
def approval_decision(approval_id):
	data = request.get_json(silent=True)
	if not isinstance(data, dict):
		data = {}
	try:
		result = decide_approval(
			approval_id,
			session["user_id"],
			data.get("decision"),
			data.get("comments"),
		)
	except WorkflowError as error:
		return jsonify(error=str(error)), error.status
	return jsonify(**result), 200
