import { apiRequest } from "./http";

const TYPE_LABELS = {
  equipment_assignment: "Equipment assignment",
  equipment_procurement: "Equipment procurement",
  tool_assignment: "Tool assignment",
  escalation: "Escalation",
  disbursement: "Disbursement",
};

function mapApproval(item) {
  return {
    id: item.approval_id,
    requestType: item.request_type,
    typeLabel: TYPE_LABELS[item.request_type] || item.request_type,
    summary: item.summary,
    referenceId: item.reference_id,
    requestedBy: item.requested_by_name,
    status: "pending", // /approvals/pending only returns pending items
    createdAt: item.created_at,
  };
}

export async function getApprovals() {
  const { approvals } = await apiRequest("/approvals/pending");
  return approvals.map(mapApproval);
}

export async function decideApproval(id, decision, reason) {
  return apiRequest(`/approvals/${id}/decision`, {
    method: "POST",
    body: { decision, reason },
  });
}