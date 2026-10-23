from contextlib import contextmanager

import pytest

from backend.services import workflow


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, project, milestone=None, approvers=None):
        self.project = project
        self.milestone = milestone
        self.approvers = approvers
        self.statements = []
        self.staff = []
        self.approval_requests = []
        self.notifications = []

    def execute(self, statement, params=()):
        self.statements.append((statement, params))
        if 'SELECT user_id, username, role FROM "Users"' in statement:
            return FakeResult(rows=self.approvers)
        if 'FROM "Projects" p' in statement:
            return FakeResult(self.project)
        if 'SELECT user_id, role, is_active FROM "Users"' in statement:
            return FakeResult(rows=self.approvers)
        if 'SELECT COALESCE(MAX(round_number)' in statement:
            return FakeResult({"round_number": 0})
        if 'INSERT INTO "Approval_Requests"' in statement:
            self.approval_requests.append(params)
            return FakeResult()
        if 'SELECT 1 FROM "Project_Staff_Assignments"' in statement:
            return FakeResult(
                {"exists": 1}
                if any(member["user_id"] == params[1] for member in self.staff)
                else None
            )
        if 'SELECT user_id FROM "Project_Staff_Assignments"' in statement:
            return FakeResult(rows=[{"user_id": member["user_id"]} for member in self.staff])
        if 'INSERT INTO "Notifications"' in statement:
            self.notifications.append(params)
            return FakeResult()
        if 'WHERE user_id = ANY(%s)' in statement:
            staff_ids = params[0]
            return FakeResult(rows=[{"user_id": staff_id} for staff_id in staff_ids])
        if 'SELECT user_id FROM "Users"' in statement:
            return FakeResult({"user_id": params[0]})
        if 'UPDATE "Projects" SET manager_id' in statement:
            self.project["manager_id"] = params[0]
            return FakeResult(self.project)
        if "SET status = 'pending_approval'" in statement:
            return FakeResult({**self.project, "status": "pending_approval"})
        if 'UPDATE "Projects" SET status' in statement:
            return FakeResult({**self.project, "status": params[0]})
        if 'INSERT INTO "Project_Status_History"' in statement:
            return FakeResult()
        if 'DELETE FROM "Project_Staff_Assignments"' in statement:
            self.staff = []
            return FakeResult()
        if 'INSERT INTO "Project_Staff_Assignments"' in statement:
            self.staff.append({"user_id": params[1], "username": f"staff{params[1]}", "role": "staff"})
            return FakeResult()
        if 'FROM "Project_Staff_Assignments" a' in statement:
            return FakeResult(rows=self.staff)
        if 'INSERT INTO "Project_Milestones"' in statement:
            return FakeResult(self.milestone)
        raise AssertionError(f"Unexpected SQL: {statement}")


def install_fake_connection(monkeypatch, connection):
    @contextmanager
    def connect_database():
        yield connection

    monkeypatch.setattr(workflow, "connect_database", connect_database)


def test_assigned_staff_project_manager_can_add_milestone(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": "active"}
    milestone = {"milestone_id": 8, "project_id": 17, "title": "Safety review"}
    connection = FakeConnection(project, milestone)
    install_fake_connection(monkeypatch, connection)

    result = workflow.add_project_milestone(
        17,
        {"title": "Safety review", "description": "Inspect controls", "due_date": "2026-11-02"},
        4,
        "staff",
    )

    assert result == milestone
    assert any('INSERT INTO "Project_Milestones"' in statement for statement, _ in connection.statements)


def test_global_admin_can_add_milestone(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": "active"}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    workflow.add_project_milestone(17, {"title": "Safety review"}, 9, "admin")

    assert any('INSERT INTO "Project_Milestones"' in statement for statement, _ in connection.statements)


def test_manager_can_add_milestone(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": "draft"}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    workflow.add_project_milestone(17, {"title": "Safety review"}, 9, "manager")

    assert any('INSERT INTO "Project_Milestones"' in statement for statement, _ in connection.statements)


def test_unassigned_staff_cannot_add_milestone(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": "active"}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError) as error:
        workflow.add_project_milestone(17, {"title": "Safety review"}, 5, "staff")

    assert error.value.status == 403
    assert not any('INSERT INTO "Project_Milestones"' in statement for statement, _ in connection.statements)


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_closed_project_rejects_milestone_changes(monkeypatch, status):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": status}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError) as error:
        workflow.add_project_milestone(17, {"title": "Safety review"}, 4, "staff")

    assert error.value.status == 409
    assert not any('INSERT INTO "Project_Milestones"' in statement for statement, _ in connection.statements)


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_closed_project_rejects_milestone_status_changes(monkeypatch, status):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": status}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError) as error:
        workflow.update_project_milestone(17, 8, {"status": "completed"}, 9, "admin")

    assert error.value.status == 409
    assert not any('UPDATE "Project_Milestones"' in statement for statement, _ in connection.statements)


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_closed_project_rejects_team_changes(monkeypatch, status):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": status}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError) as error:
        workflow.update_project_team(
            17, {"manager_id": 5, "staff_ids": [6]}, 9, "admin"
        )

    assert error.value.status == 409
    assert not any('UPDATE "Projects" SET manager_id' in statement for statement, _ in connection.statements)
    assert not any('DELETE FROM "Project_Staff_Assignments"' in statement for statement, _ in connection.statements)


@pytest.mark.parametrize("status", ["completed", "cancelled"])
def test_closed_project_rejects_project_field_changes(monkeypatch, status):
    project = {
        "project_id": 17,
        "created_by": 1,
        "manager_id": 4,
        "status": status,
        "start_date": None,
        "end_date": None,
    }
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError) as error:
        workflow.update_project(17, {"name": "Changed name"}, 9, "admin")

    assert error.value.status == 409
    assert not any('UPDATE "Projects" SET name' in statement for statement, _ in connection.statements)


def test_admin_can_assign_project_manager_before_approval(monkeypatch):
    project = {
        "project_id": 17,
        "name": "Bridge repair",
        "created_by": 1,
        "manager_id": None,
        "status": "draft",
    }
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    result = workflow.update_project_team(17, {"manager_id": 4}, 9, "admin")

    assert result["project"]["manager_id"] == 4
    assert any('UPDATE "Projects" SET manager_id' in statement for statement, _ in connection.statements)


def test_new_project_team_members_are_notified_once(monkeypatch):
    project = {
        "project_id": 17,
        "name": "Bridge repair",
        "created_by": 1,
        "manager_id": None,
        "status": "approved",
    }
    connection = FakeConnection(project)
    connection.staff = [{"user_id": 5, "username": "staff5", "role": "staff"}]
    install_fake_connection(monkeypatch, connection)

    workflow.update_project_team(
        17, {"manager_id": 4, "staff_ids": [5, 6]}, 9, "admin"
    )

    assert connection.notifications == [
        (4, "You were assigned as project manager for Bridge repair.", "project_assigned"),
        (6, "You were assigned to project Bridge repair.", "project_assigned"),
    ]


def test_draft_project_cannot_be_approved_without_approval_chain(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": None, "status": "draft"}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError, match="Cannot change project status"):
        workflow.update_project_status(17, "approved", 9, "admin")

    assert not any(
        statement.startswith('UPDATE "Projects" SET status')
        for statement, _ in connection.statements
    )

def test_draft_project_cannot_skip_directly_to_active(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": None, "status": "draft"}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError, match="Cannot change project status"):
        workflow.update_project_status(17, "active", 9, "admin")

    assert not any(
        statement.startswith('UPDATE "Projects" SET status')
        for statement, _ in connection.statements
    )


def test_project_submission_preserves_ordered_approval_chain(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": None, "status": "draft"}
    approvers = [
        {"user_id": 2, "role": "manager", "is_active": True},
        {"user_id": 3, "role": "admin", "is_active": True},
    ]
    connection = FakeConnection(project, approvers=approvers)
    install_fake_connection(monkeypatch, connection)

    result = workflow.submit_project(17, [2, 3], 1, "staff")

    assert result["status"] == "pending_approval"
    assert connection.approval_requests == [
        (17, 1, 1, 2, "pending"),
        (17, 1, 2, 3, "waiting"),
    ]
    assert any(
        'INSERT INTO "Project_Status_History"' in statement
        and params == (17, "draft", "pending_approval", 1, None)
        for statement, params in connection.statements
    )


def test_admin_can_assign_project_manager_and_staff_after_approval(monkeypatch):
    project = {
        "project_id": 17,
        "name": "Bridge repair",
        "created_by": 1,
        "manager_id": None,
        "status": "approved",
    }
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    result = workflow.update_project_team(
        17, {"manager_id": 4, "staff_ids": [5, 6]}, 9, "admin"
    )

    assert result["project"]["manager_id"] == 4
    assert [member["user_id"] for member in result["staff"]] == [5, 6]


def test_staff_cannot_assign_project_team(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": None, "status": "approved"}
    connection = FakeConnection(project)
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError) as error:
        workflow.update_project_team(17, {"staff_ids": [5]}, 5, "staff")

    assert error.value.status == 403
    assert len(connection.statements) == 0


def test_assigned_staff_can_access_project(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": "active"}
    connection = FakeConnection(project)
    connection.staff = [{"user_id": 5}]
    install_fake_connection(monkeypatch, connection)

    with workflow.connect_database() as fake_connection:
        result = workflow._project_for_user(fake_connection, 17, 5, "staff")

    assert result == project


def test_inactive_user_cannot_be_added_as_project_approver(monkeypatch):
    project = {"project_id": 17, "created_by": 1, "manager_id": 4, "status": "draft"}
    connection = FakeConnection(
        project,
        approvers=[{"user_id": 6, "role": "manager", "is_active": False}],
    )
    install_fake_connection(monkeypatch, connection)

    with pytest.raises(workflow.WorkflowError, match="inactive") as error:
        workflow.submit_project(17, [6], 1, "staff")

    assert error.value.status == 400
    assert not any('INSERT INTO "Approval_Requests"' in statement for statement, _ in connection.statements)


def test_project_approver_list_excludes_current_user(monkeypatch):
    approvers = [
        {"user_id": 2, "username": "manager", "role": "manager"},
        {"user_id": 3, "username": "admin", "role": "admin"},
    ]
    connection = FakeConnection(None, approvers=approvers)
    install_fake_connection(monkeypatch, connection)

    result = workflow.list_project_approvers(1)

    assert result == approvers
    statement, params = connection.statements[0]
    assert 'is_active = TRUE AND role IN' in statement
    assert 'AND user_id <> %s' in statement
    assert params == (1,)