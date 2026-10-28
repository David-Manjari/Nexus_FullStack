"""Project lifecycle and sequential approval-chain operations."""

from datetime import date

from ..admin_accounts import connect_database
from .notifications import create_notification


class WorkflowError(Exception):
	"""An expected project workflow failure with an HTTP status code."""

	def __init__(self, message, status=400):
		super().__init__(message)
		self.status = status


PROJECT_FIELDS = {"name", "description", "start_date", "end_date"}
PROJECT_STATUSES = {
	"approved", "active", "on_hold", "completed", "cancelled"
}
MILESTONE_STATUSES = {"planned", "in_progress", "completed"}
STATUS_TRANSITIONS = {
	"approved": {"active", "cancelled"},
	"active": {"on_hold", "completed", "cancelled"},
	"on_hold": {"active", "completed", "cancelled"},
}
CLOSED_PROJECT_STATUSES = {"completed", "cancelled"}


def _parse_date(value, field):
	if value in (None, ""):
		return None
	if isinstance(value, date):
		return value
	if not isinstance(value, str):
		raise WorkflowError(f"{field} must use YYYY-MM-DD format.")
	try:
		return date.fromisoformat(value)
	except ValueError as error:
		raise WorkflowError(f"{field} must use YYYY-MM-DD format.") from error


def _project_for_user(connection, project_id, user_id, role, *, lock=False):
	suffix = " FOR UPDATE" if lock else ""
	project = connection.execute(
		f'''SELECT p.*, u.role AS creator_role
			FROM "Projects" p
			JOIN "Users" u ON u.user_id = p.created_by
			WHERE p.project_id = %s{suffix}''',
		(project_id,),
	).fetchone()
	if project is None:
		raise WorkflowError("Project not found.", 404)
	if (project["created_by"] != user_id and project["manager_id"] != user_id
			and role not in ("admin", "manager")):
		staff_assignment = connection.execute(
			'''SELECT 1 FROM "Project_Staff_Assignments"
			   WHERE project_id = %s AND user_id = %s''',
			(project_id, user_id),
		).fetchone()
		if staff_assignment is None:
			raise WorkflowError("You cannot access this project.", 403)
	return project


def _ensure_project_open(project):
	if project["status"] in CLOSED_PROJECT_STATUSES:
		raise WorkflowError("Completed or cancelled projects cannot be edited.", 409)


def _record_status(connection, project_id, from_status, to_status, user_id, reason=None):
	if from_status == to_status:
		return
	connection.execute(
		'''INSERT INTO "Project_Status_History"
			   (project_id, from_status, to_status, changed_by, reason)
		   VALUES (%s, %s, %s, %s, %s)''',
		(project_id, from_status, to_status, user_id, reason),
	)


def create_project(data, user_id):
	name = data.get("name")
	if not isinstance(name, str) or not name.strip():
		raise WorkflowError("name is required.")
	start_date = _parse_date(data.get("start_date"), "start_date")
	end_date = _parse_date(data.get("end_date"), "end_date")
	if start_date and end_date and end_date < start_date:
		raise WorkflowError("end_date cannot be before start_date.")
	description = data.get("description")
	if description is not None and not isinstance(description, str):
		raise WorkflowError("description must be text.")

	with connect_database() as connection:
		project = connection.execute(
			'''INSERT INTO "Projects"
				   (name, description, start_date, end_date, created_by)
			   VALUES (%s, %s, %s, %s, %s)
			   RETURNING *''',
			(name.strip(), description, start_date, end_date, user_id),
		).fetchone()
		_record_status(connection, project["project_id"], None, "draft", user_id)
		return project


def list_projects(user_id, role, assigned_only=False):
	with connect_database() as connection:
		query = '''SELECT p.*, creator.username AS created_by_name,
					  manager.username AS manager_name,
					  COALESCE((
						  SELECT json_agg(row_to_json(audit)
							  ORDER BY audit.changed_at DESC, audit.history_id DESC)
						  FROM (
							  SELECT h.history_id, h.from_status, h.to_status,
									 h.reason, h.changed_by,
									 changed_by.username AS changed_by_name,
									 h.changed_at
							  FROM "Project_Status_History" h
							  JOIN "Users" changed_by ON changed_by.user_id = h.changed_by
							  WHERE h.project_id = p.project_id
							  ORDER BY h.changed_at DESC, h.history_id DESC
							  LIMIT 5
						  ) AS audit
					  ), '[]'::json) AS status_audit
			   FROM "Projects" p
			   JOIN "Users" creator ON creator.user_id = p.created_by
			   LEFT JOIN "Users" manager ON manager.user_id = p.manager_id
			   '''
		params = ()
		if assigned_only:
			query += ''' WHERE EXISTS (
				 SELECT 1 FROM "Project_Staff_Assignments" assigned_staff
				 WHERE assigned_staff.project_id = p.project_id
				   AND assigned_staff.user_id = %s
			 )'''
			params = (user_id,)
		elif role not in ("admin", "manager"):
			query += ''' WHERE p.created_by = %s OR p.manager_id = %s
				 OR EXISTS (
					 SELECT 1 FROM "Project_Staff_Assignments" assigned_staff
					 WHERE assigned_staff.project_id = p.project_id
					   AND assigned_staff.user_id = %s
				 )'''
			params = (user_id, user_id, user_id)
		query += " ORDER BY p.created_at DESC, p.project_id DESC"
		return connection.execute(query, params).fetchall()


def get_project(project_id, user_id, role):
	with connect_database() as connection:
		project = _project_for_user(connection, project_id, user_id, role)
		approval_chain = connection.execute(
			'''SELECT a.approval_id, a.round_number, a.step_order,
					  a.approver_id, u.username AS approver_name,
					  a.status, a.comments, a.created_at, a.decided_at
			   FROM "Approval_Requests" a
			   JOIN "Users" u ON u.user_id = a.approver_id
			   WHERE a.project_id = %s
			   ORDER BY a.round_number DESC, a.step_order''',
			(project_id,),
		).fetchall()
		status_history = connection.execute(
			'''SELECT h.history_id, h.from_status, h.to_status, h.reason,
					  h.changed_by, u.username AS changed_by_name, h.changed_at
			   FROM "Project_Status_History" h
			   JOIN "Users" u ON u.user_id = h.changed_by
			   WHERE h.project_id = %s
			   ORDER BY h.changed_at DESC, h.history_id DESC''',
			(project_id,),
		).fetchall()
		milestones = connection.execute(
			'''SELECT m.milestone_id, m.title, m.description, m.due_date,
					  m.status, m.created_by, u.username AS created_by_name,
					  m.created_at, m.updated_at, m.completed_at
			   FROM "Project_Milestones" m
			   JOIN "Users" u ON u.user_id = m.created_by
			   WHERE m.project_id = %s
			   ORDER BY m.due_date NULLS LAST, m.created_at, m.milestone_id''',
			(project_id,),
		).fetchall()
		staff = connection.execute(
			'''SELECT u.user_id, u.username, u.role
			   FROM "Project_Staff_Assignments" a
			   JOIN "Users" u ON u.user_id = a.user_id
			   WHERE a.project_id = %s ORDER BY u.username''',
			(project_id,),
		).fetchall()
	return {
		"project": project,
		"approval_chain": approval_chain,
		"status_history": status_history,
		"milestones": milestones,
		"staff": staff,
	}


def update_project(project_id, data, user_id, role):
	fields = {}
	for field in PROJECT_FIELDS:
		if field not in data:
			continue
		value = data[field]
		if field == "name":
			if not isinstance(value, str) or not value.strip():
				raise WorkflowError("name cannot be empty.")
			value = value.strip()
		elif field == "description":
			if value is not None and not isinstance(value, str):
				raise WorkflowError("description must be text.")
		else:
			value = _parse_date(value, field)
		fields[field] = value
	if not fields:
		raise WorkflowError("Provide at least one editable project field.")

	with connect_database() as connection:
		project = _project_for_user(connection, project_id, user_id, role, lock=True)
		_ensure_project_open(project)
		if project["status"] != "draft":
			raise WorkflowError("Only draft projects can be edited.", 409)
		start_date = fields.get("start_date", project["start_date"])
		end_date = fields.get("end_date", project["end_date"])
		if start_date and end_date and end_date < start_date:
			raise WorkflowError("end_date cannot be before start_date.")
		assignments = ", ".join(f"{field} = %s" for field in fields)
		return connection.execute(
			f'''UPDATE "Projects" SET {assignments}, updated_at = NOW()
				WHERE project_id = %s RETURNING *''',
			(*fields.values(), project_id),
		).fetchone()


def list_project_assignable_users():
	with connect_database() as connection:
		return connection.execute(
			'''SELECT user_id, username, role FROM "Users"
			   WHERE is_active = TRUE AND role IN ('admin', 'manager', 'staff')
			   ORDER BY username'''
		).fetchall()


def list_project_approvers(user_id):
	with connect_database() as connection:
		return connection.execute(
			'''SELECT user_id, username, role FROM "Users"
			   WHERE is_active = TRUE AND role IN ('admin', 'manager')
			     AND user_id <> %s
			   ORDER BY username''',
			(user_id,),
		).fetchall()


def update_project_team(project_id, data, user_id, role):
	if role not in ("admin", "manager"):
		raise WorkflowError("Only admins and managers can assign project staff.", 403)
	if not data or set(data) - {"manager_id", "staff_ids"}:
		raise WorkflowError("Provide manager_id, staff_ids, or both.")

	manager_id = data.get("manager_id")
	if "manager_id" in data and manager_id is not None:
		if type(manager_id) is not int or manager_id <= 0:
			raise WorkflowError("manager_id must be a positive user ID or null.")
	staff_ids = data.get("staff_ids")
	if "staff_ids" in data:
		if (not isinstance(staff_ids, list)
				or any(type(staff_id) is not int or staff_id <= 0 for staff_id in staff_ids)):
			raise WorkflowError("staff_ids must be a list of positive user IDs.")
		if len(set(staff_ids)) != len(staff_ids):
			raise WorkflowError("A staff member can only be assigned once.")

	with connect_database() as connection:
		project = _project_for_user(connection, project_id, user_id, role, lock=True)
		_ensure_project_open(project)
		previous_manager_id = project.get("manager_id")
		previous_staff_ids = set()
		if "staff_ids" in data:
			previous_staff_ids = {
				row["user_id"]
				for row in connection.execute(
					'''SELECT user_id FROM "Project_Staff_Assignments"
					   WHERE project_id = %s''',
					(project_id,),
				).fetchall()
			}
		if "manager_id" in data and manager_id is not None:
			manager = connection.execute(
				'''SELECT user_id FROM "Users"
				   WHERE user_id = %s AND is_active = TRUE
					 AND role IN ('admin', 'manager', 'staff')''',
				(manager_id,),
			).fetchone()
			if manager is None:
				raise WorkflowError("Project manager must be an active user.")
		if "staff_ids" in data:
			staff = connection.execute(
				'''SELECT user_id FROM "Users"
				   WHERE user_id = ANY(%s) AND is_active = TRUE AND role = 'staff' ''',
				(staff_ids,),
			).fetchall()
			if len(staff) != len(staff_ids):
				raise WorkflowError("Every assigned staff member must be active and have the staff role.")

		if "manager_id" in data:
			project = connection.execute(
				'''UPDATE "Projects" SET manager_id = %s, updated_at = NOW()
				   WHERE project_id = %s RETURNING *''',
				(manager_id, project_id),
			).fetchone()
			if manager_id is not None and manager_id != previous_manager_id:
				create_notification(
					connection,
					manager_id,
					f"You were assigned as project manager for {project['name']}.",
					"project_assigned",
				)
		if "staff_ids" in data:
			connection.execute(
				'''DELETE FROM "Project_Staff_Assignments" WHERE project_id = %s''',
				(project_id,),
			)
			for staff_id in staff_ids:
				connection.execute(
					'''INSERT INTO "Project_Staff_Assignments"
						   (project_id, user_id, assigned_by)
					   VALUES (%s, %s, %s)''',
					(project_id, staff_id, user_id),
				)
				if staff_id not in previous_staff_ids:
					create_notification(
						connection,
						staff_id,
						f"You were assigned to project {project['name']}.",
						"project_assigned",
					)
		assigned_staff = connection.execute(
			'''SELECT u.user_id, u.username, u.role
			   FROM "Project_Staff_Assignments" a
			   JOIN "Users" u ON u.user_id = a.user_id
			   WHERE a.project_id = %s ORDER BY u.username''',
			(project_id,),
		).fetchall()
		return {"project": project, "staff": assigned_staff}


def submit_project(project_id, approver_ids, user_id, role):
	if not isinstance(approver_ids, list) or not approver_ids:
		raise WorkflowError("approver_ids must be a non-empty ordered list.")
	if any(type(value) is not int or value <= 0 for value in approver_ids):
		raise WorkflowError("Every approver ID must be a positive integer.")
	if len(set(approver_ids)) != len(approver_ids):
		raise WorkflowError("An approver can appear only once in a chain.")

	with connect_database() as connection:
		project = _project_for_user(connection, project_id, user_id, role, lock=True)
		if project["status"] not in ("draft", "rejected"):
			raise WorkflowError("Only draft or rejected projects can be submitted.", 409)
		approvers = connection.execute(
			'''SELECT user_id, role, is_active FROM "Users"
			   WHERE user_id = ANY(%s)''',
			(approver_ids,),
		).fetchall()
		approvers_by_id = {approver["user_id"]: approver for approver in approvers}
		if len(approvers_by_id) != len(approver_ids):
			raise WorkflowError("One or more approvers do not exist or are inactive.")
		if any(not approvers_by_id[approver_id]["is_active"]
			   for approver_id in approver_ids):
			raise WorkflowError("One or more approvers do not exist or are inactive.")
		if project_id and project["created_by"] in approver_ids:
			raise WorkflowError("A project creator cannot approve their own project.")
		if any(approvers_by_id[approver_id]["role"] not in ("manager", "admin")
			   for approver_id in approver_ids):
			raise WorkflowError("Approvers must have the manager or admin role.")

		current_round = connection.execute(
			'''SELECT COALESCE(MAX(round_number), 0) AS round_number
			   FROM "Approval_Requests" WHERE project_id = %s''',
			(project_id,),
		).fetchone()["round_number"]
		round_number = current_round + 1
		for step_order, approver_id in enumerate(approver_ids, start=1):
			connection.execute(
				'''INSERT INTO "Approval_Requests"
					   (project_id, round_number, step_order, approver_id, status)
				   VALUES (%s, %s, %s, %s, %s)''',
				(project_id, round_number, step_order, approver_id,
				 "pending" if step_order == 1 else "waiting"),
			)
		result = connection.execute(
			'''UPDATE "Projects"
			   SET status = 'pending_approval', updated_at = NOW()
			   WHERE project_id = %s RETURNING *''',
			(project_id,),
		).fetchone()
		_record_status(
			connection, project_id, project["status"], "pending_approval", user_id
		)
		return result


def update_project_status(project_id, status, user_id, role, reason=None):
	if not isinstance(status, str) or status not in PROJECT_STATUSES:
		raise WorkflowError(f"status must be one of: {', '.join(sorted(PROJECT_STATUSES))}.")
	if reason is not None and not isinstance(reason, str):
		raise WorkflowError("reason must be text.")
	with connect_database() as connection:
		project = _project_for_user(connection, project_id, user_id, role, lock=True)
		_ensure_project_open(project)
		if project["manager_id"] != user_id and role not in ("manager", "admin"):
			raise WorkflowError("Only this project's manager can change its status.", 403)
		allowed = STATUS_TRANSITIONS.get(project["status"], set())
		if status not in allowed:
			raise WorkflowError(
				f"Cannot change project status from {project['status']} to {status}.", 409
			)
		result = connection.execute(
			'''UPDATE "Projects" SET status = %s, updated_at = NOW()
			   WHERE project_id = %s RETURNING *''',
			(status, project_id),
		).fetchone()
		_record_status(
			connection, project_id, project["status"], status, user_id, reason
		)
		return result


def add_project_milestone(project_id, data, user_id, role):
	title = data.get("title")
	if not isinstance(title, str) or not title.strip():
		raise WorkflowError("title is required.")
	description = data.get("description")
	if description is not None and not isinstance(description, str):
		raise WorkflowError("description must be text.")
	due_date = _parse_date(data.get("due_date"), "due_date")

	with connect_database() as connection:
		project = _project_for_user(connection, project_id, user_id, role, lock=True)
		_ensure_project_open(project)
		if project["manager_id"] != user_id and role not in ("admin", "manager"):
			raise WorkflowError("Only admins, managers, and this project's manager can add milestones.", 403)
		return connection.execute(
			'''INSERT INTO "Project_Milestones"
				   (project_id, title, description, due_date, created_by)
			   VALUES (%s, %s, %s, %s, %s)
			   RETURNING milestone_id, project_id, title, description, due_date,
						 status, created_by, created_at, updated_at, completed_at''',
			(project_id, title.strip(), description, due_date, user_id),
		).fetchone()


def update_project_milestone(project_id, milestone_id, data, user_id, role):
	status = data.get("status")
	if not isinstance(status, str) or status not in MILESTONE_STATUSES:
		raise WorkflowError(
			f"status must be one of: {', '.join(sorted(MILESTONE_STATUSES))}."
		)

	with connect_database() as connection:
		project = _project_for_user(connection, project_id, user_id, role, lock=True)
		_ensure_project_open(project)
		if project["manager_id"] != user_id and role not in ("admin", "manager"):
			raise WorkflowError("Only admins, managers, and this project's manager can update milestones.", 403)
		milestone = connection.execute(
			'''SELECT milestone_id FROM "Project_Milestones"
			   WHERE milestone_id = %s AND project_id = %s''',
			(milestone_id, project_id),
		).fetchone()
		if milestone is None:
			raise WorkflowError("Milestone not found.", 404)
		return connection.execute(
			'''UPDATE "Project_Milestones"
			   SET status = %s,
				   completed_at = CASE WHEN %s = 'completed' THEN NOW() ELSE NULL END,
				   updated_at = NOW()
			   WHERE milestone_id = %s AND project_id = %s
			   RETURNING milestone_id, project_id, title, description, due_date,
						 status, created_by, created_at, updated_at, completed_at''',
			(status, status, milestone_id, project_id),
		).fetchone()


def list_my_approvals(approver_id):
	with connect_database() as connection:
		return connection.execute(
			'''SELECT a.approval_id, a.project_id, p.name AS project_name,
					  a.round_number, a.step_order, a.status, a.created_at
			   FROM "Approval_Requests" a
			   JOIN "Projects" p ON p.project_id = a.project_id
			   WHERE a.approver_id = %s AND a.status = 'pending'
			   ORDER BY a.created_at, a.project_id, a.step_order''',
			(approver_id,),
		).fetchall()


def decide_approval(approval_id, approver_id, decision, comments=None):
	if decision not in ("approved", "rejected"):
		raise WorkflowError("decision must be approved or rejected.")
	if comments is not None and not isinstance(comments, str):
		raise WorkflowError("comments must be text.")

	with connect_database() as connection:
		reference = connection.execute(
			'''SELECT project_id FROM "Approval_Requests" WHERE approval_id = %s''',
			(approval_id,),
		).fetchone()
		if reference is None:
			raise WorkflowError("Approval not found.", 404)
		project = connection.execute(
			'''SELECT status FROM "Projects" WHERE project_id = %s FOR UPDATE''',
			(reference["project_id"],),
		).fetchone()
		approval = connection.execute(
			'''SELECT * FROM "Approval_Requests" WHERE approval_id = %s FOR UPDATE''',
			(approval_id,),
		).fetchone()
		if approval["approver_id"] != approver_id:
			raise WorkflowError("This approval is assigned to another user.", 403)
		if approval["status"] != "pending" or project["status"] != "pending_approval":
			raise WorkflowError("This approval is no longer pending.", 409)

		connection.execute(
			'''UPDATE "Approval_Requests"
			   SET status = %s, comments = %s, decided_at = NOW()
			   WHERE approval_id = %s''',
			(decision, comments, approval_id),
		)

		if decision == "rejected":
			connection.execute(
				'''UPDATE "Approval_Requests" SET status = 'skipped'
				   WHERE project_id = %s AND round_number = %s
					 AND step_order > %s AND status = 'waiting' ''',
				(approval["project_id"], approval["round_number"], approval["step_order"]),
			)
			project_status = "rejected"
		else:
			next_approval = connection.execute(
				'''SELECT approval_id FROM "Approval_Requests"
				   WHERE project_id = %s AND round_number = %s
					 AND step_order > %s AND status = 'waiting'
				   ORDER BY step_order LIMIT 1''',
				(approval["project_id"], approval["round_number"], approval["step_order"]),
			).fetchone()
			if next_approval:
				connection.execute(
					'''UPDATE "Approval_Requests" SET status = 'pending'
					   WHERE approval_id = %s''',
					(next_approval["approval_id"],),
				)
				project_status = "pending_approval"
			else:
				project_status = "approved"

		result = connection.execute(
			'''UPDATE "Projects" SET status = %s, updated_at = NOW()
			   WHERE project_id = %s RETURNING *''',
			(project_status, approval["project_id"]),
		).fetchone()
		_record_status(
			connection,
			approval["project_id"],
			project["status"],
			project_status,
			approver_id,
			comments,
		)
	return {"project": result, "decision": decision}
