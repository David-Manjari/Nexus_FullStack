"""Project creation, tracking, and approval-chain routes."""

from flask import Blueprint, jsonify, request, session

from ..auth import roles_required
from ..services.workflow import (
	WorkflowError,
	create_project,
	get_project,
	list_projects,
	submit_project,
	update_project,
	update_project_status,
)


projects_bp = Blueprint("projects", __name__)
PROJECT_ROLES = ("admin", "manager", "store_manager", "staff")


def _payload():
	data = request.get_json(silent=True)
	return data if isinstance(data, dict) else {}


def _run(operation, *, success_key=None, status=200):
	try:
		result = operation()
	except WorkflowError as error:
		return jsonify(error=str(error)), error.status
	if success_key:
		return jsonify(**{success_key: result}), status
	return jsonify(result), status


@projects_bp.get("")
@roles_required(*PROJECT_ROLES)
def projects_list():
	return _run(
		lambda: list_projects(session["user_id"], session["role"]),
		success_key="projects",
	)


@projects_bp.post("")
@roles_required(*PROJECT_ROLES)
def projects_create():
	return _run(
		lambda: create_project(_payload(), session["user_id"]),
		success_key="project",
		status=201,
	)


@projects_bp.get("/<int:project_id>")
@roles_required(*PROJECT_ROLES)
def projects_get(project_id):
	return _run(
		lambda: get_project(project_id, session["user_id"], session["role"])
	)


@projects_bp.patch("/<int:project_id>")
@roles_required(*PROJECT_ROLES)
def projects_update(project_id):
	return _run(
		lambda: update_project(
			project_id, _payload(), session["user_id"], session["role"]
		),
		success_key="project",
	)


@projects_bp.post("/<int:project_id>/submit")
@roles_required(*PROJECT_ROLES)
def projects_submit(project_id):
	return _run(
		lambda: submit_project(
			project_id,
			_payload().get("approver_ids"),
			session["user_id"],
			session["role"],
		),
		success_key="project",
	)


@projects_bp.patch("/<int:project_id>/status")
@roles_required("admin", "manager")
def projects_update_status(project_id):
	data = _payload()
	return _run(
		lambda: update_project_status(
			project_id,
			data.get("status"),
			session["user_id"],
			session["role"],
			data.get("reason"),
		),
		success_key="project",
	)
