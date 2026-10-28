import { apiRequest } from "./http";

function mapProject(project) {
  return {
    id: project.project_id,
    name: project.name,
    description: project.description ?? "",
    status: project.status,
    managerId: project.manager_id,
    managerName: project.manager_name,
    startDate: project.start_date,
    endDate: project.end_date,
    createdAt: project.created_at,
    statusAudit: (project.status_audit ?? []).map(mapStatusAudit),
  };
}

function mapStatusAudit(entry) {
  return {
    id: entry.history_id,
    fromStatus: entry.from_status,
    toStatus: entry.to_status,
    reason: entry.reason,
    changedByName: entry.changed_by_name,
    changedAt: entry.changed_at,
  };
}

function mapMilestone(milestone) {
  return {
    id: milestone.milestone_id,
    title: milestone.title,
    description: milestone.description ?? "",
    dueDate: milestone.due_date,
    status: milestone.status,
    createdByName: milestone.created_by_name,
    createdAt: milestone.created_at,
    completedAt: milestone.completed_at,
  };
}

export async function getProjects() {
  const { projects } = await apiRequest("/projects");
  return projects.map(mapProject);
}

export async function getAssignedProjects() {
  const { projects } = await apiRequest("/projects/assigned");
  return projects.map(mapProject);
}

export async function getProjectDetails(projectId) {
  const {
    project,
    approval_chain: approvalChain,
    status_history: statusHistory,
    milestones,
    staff,
  } = await apiRequest(
    `/projects/${projectId}`
  );
  return {
    project: mapProject(project),
    approvalChain: approvalChain.map((entry) => ({
      id: entry.approval_id,
      roundNumber: entry.round_number,
      stepOrder: entry.step_order,
      approverId: entry.approver_id,
      approverName: entry.approver_name,
      status: entry.status,
      comments: entry.comments,
      createdAt: entry.created_at,
      decidedAt: entry.decided_at,
    })),
    statusHistory: statusHistory.map(mapStatusAudit),
    milestones: milestones.map(mapMilestone),
    staff: staff.map((member) => ({
      id: member.user_id,
      name: member.username,
      role: member.role,
    })),
  };
}

export async function getProjectApprovers() {
  const { users } = await apiRequest("/projects/approvers");
  return users.map((user) => ({
    id: user.user_id,
    name: user.username,
    role: user.role,
  }));
}

export async function getProjectAssignableUsers() {
  const { users } = await apiRequest("/projects/assignable-users");
  return users.map((user) => ({
    id: user.user_id,
    name: user.username,
    role: user.role,
  }));
}

export async function createProject(fields) {
  const { project } = await apiRequest("/projects", {
    method: "POST",
    body: {
      name: fields.name,
      description: fields.description,
      start_date: fields.startDate || null,
      end_date: fields.endDate || null,
    },
  });
  return mapProject(project);
}

export async function submitProject(projectId, approverIds) {
  const { project } = await apiRequest(`/projects/${projectId}/submit`, {
    method: "POST",
    body: { approver_ids: approverIds },
  });
  return mapProject(project);
}

export async function updateProjectStatus(projectId, status, reason) {
  const { project } = await apiRequest(`/projects/${projectId}/status`, {
    method: "PATCH",
    body: { status, reason },
  });
  return mapProject(project);
}

export async function updateProjectTeam(projectId, team) {
  return apiRequest(`/projects/${projectId}/team`, {
    method: "PATCH",
    body: team,
  });
}

export async function addProjectMilestone(projectId, fields) {
  const { milestone } = await apiRequest(`/projects/${projectId}/milestones`, {
    method: "POST",
    body: {
      title: fields.title,
      description: fields.description,
      due_date: fields.dueDate || null,
    },
  });
  return mapMilestone(milestone);
}

export async function updateProjectMilestone(projectId, milestoneId, status) {
  const { milestone } = await apiRequest(
    `/projects/${projectId}/milestones/${milestoneId}`,
    { method: "PATCH", body: { status } }
  );
  return mapMilestone(milestone);
}