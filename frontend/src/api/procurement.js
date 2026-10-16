import { apiRequest } from "./http";

function mapProcurement(item) {
  return {
    id: item.procurement_id,
    requestId: item.request_id,
    itemName: item.item_name,
    itemType: item.asset_type,
    quantity: item.quantity,
    estimatedCost: item.estimated_cost,
    supplier: item.supplier ?? "",
    notes: item.reason ?? "",
    status: item.status,
    createdBy: item.raised_by_name,
    createdAt: item.created_at,
    history: (item.history ?? []).map((entry) => ({
      status: entry.status,
      note: entry.note,
      by: entry.by,
      at: entry.at,
    })),
  };
}

function toPayload(fields) {
  // Keep backend field names at the request boundary.
  return {
    item_name: fields.itemName,
    asset_type: fields.itemType,
    quantity: Number(fields.quantity),
    estimated_cost: fields.estimatedCost === "" ? null : Number(fields.estimatedCost),
    supplier: fields.supplier,
    reason: fields.notes,
  };
}

export async function getProcurements() {
  const { procurements } = await apiRequest("/procurements");
  return procurements.map(mapProcurement);
}

export async function getProcurementById(id) {
  const { procurement } = await apiRequest(`/procurements/${id}`);
  return mapProcurement(procurement);
}

export async function createProcurement(fields) {
  const { procurement } = await apiRequest("/procurements", {
    method: "POST",
    body: toPayload(fields),
  });
  return mapProcurement(procurement);
}

export async function updateProcurement(id, fields) {
  const { procurement } = await apiRequest(`/procurements/${id}`, {
    method: "PATCH",
    body: toPayload(fields),
  });
  return mapProcurement(procurement);
}

export async function escalateProcurement(id) {
  const { procurement } = await apiRequest(`/procurements/${id}`, {
    method: "PATCH",
    body: { action: "submit" },
  });
  return mapProcurement(procurement);
}

export async function getProcurementsAwaitingApproval() {
  const items = await getProcurements();
  return items.filter((item) => item.status === "pending_approval");
}
