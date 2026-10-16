import { apiRequest } from "./http";

function mapApproval(item) {
  return {
    id: item.approval_id,
    projectId: item.project_id,
    projectName: item.project_name,
    round: item.round_number,
    step: item.step_order,
    status: item.status,
    createdAt: item.created_at,
  };
}

export async function getApprovals() {
  const { approvals } = await apiRequest("/approvals/inbox");
  return approvals.map(mapApproval);
}

export async function decideApproval(id, decision, comments) {
  return apiRequest(`/approvals/${id}/decision`, {
    method: "POST",
    body: { decision, comments },
  });
}