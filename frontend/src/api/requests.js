import { apiRequest } from "./http";
import { getItems } from "./inventory";

function mapRequest(request) {
  return {
    id: request.request_id,
    userId: request.requested_by,
    requestedBy: request.requester_name,
    itemId: request.asset_id,
    itemName: request.item_name ?? request.request_type,
    itemType: request.asset_type ?? request.request_type,
    quantity: request.quantity,
    reason: request.reason,
    neededBy: request.needed_by,
    status: request.status === "converted" ? "procurement" : request.status,
    createdAt: request.created_at,
    history: (request.history ?? []).map((entry) => ({
      status: entry.status,
      note: entry.note,
      by: entry.by,
      at: entry.at,
    })),
  };
}

export async function getRequestableItems() {
  const groups = await Promise.all(["tool", "device", "vehicle"].map((type) => getItems(type)));
  return groups.flat();
}

// Flask scopes this route to the authenticated user's session and role.
export async function getMyRequests() {
  const { requests } = await apiRequest("/requests");
  return requests.map(mapRequest);
}

export async function getIncomingRequests() {
  const { requests } = await apiRequest("/requests?status=escalated");
  return requests.map(mapRequest);
}

export async function createRequest({ itemId, quantity, reason, neededBy }) {
  const { request, procurement } = await apiRequest("/requests", {
    method: "POST",
    // Convert form camelCase and IDs to the backend's required asset request fields.
    body: {
      request_type: "asset",
      asset_id: Number(itemId),
      quantity: Number(quantity),
      reason: String(reason).trim(),
      needed_by: neededBy || null,
    },
  });
  return { ...mapRequest(request), procurement };
}
