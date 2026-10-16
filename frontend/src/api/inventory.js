import { API_BASE_URL } from "./config";
import { apiRequest } from "./http";

function mapAsset(asset) {
  return {
    id: String(asset.asset_id),
    type: asset.asset_type,
    name: asset.name,
    category: asset.category ?? "",
    brand: asset.brand ?? "",
    sku: asset.serial_no ?? "",
    image: asset.image_url ? new URL(asset.image_url, API_BASE_URL).toString() : "",
    status: asset.status,
    assignedTo: asset.assigned_to_user_id ?? null,
    assignmentId: asset.current_assignment_id ?? null,
    plateNo: asset.plate_no ?? "",
    make: asset.make ?? "",
    model: asset.model ?? "",
    mileage: asset.mileage ?? 0,
  };
}

export async function getItems(type, { signal } = {}) {
  const query = type ? `?type=${encodeURIComponent(type)}` : "";
  const { assets } = await apiRequest(`/assets${query}`, { signal });
  return assets.map(mapAsset);
}

export async function createItem(type, data) {
  const payload = {
    asset_type: type,
    name: data.name,
    category: data.category,
    brand: data.brand,
    serial_no: data.sku,
    condition: data.condition,
  };
  if (type === "vehicle") {
    payload.plate_no = data.plateNo;
    payload.make = data.make;
    payload.model = data.model;
    payload.mileage = Number(data.mileage || 0);
  }
  const { asset } = await apiRequest("/assets", { method: "POST", body: payload });
  return mapAsset(asset);
}

export async function updateItem(id, changes) {
  const payload = {};
  const fields = {
    name: "name", category: "category", brand: "brand", sku: "serial_no",
    status: "status", condition: "condition", plateNo: "plate_no",
    make: "make", model: "model", mileage: "mileage",
  };
  for (const [source, target] of Object.entries(fields)) {
    if (source in changes) payload[target] = changes[source];
  }
  const { asset } = await apiRequest(`/assets/${id}`, { method: "PATCH", body: payload });
  return mapAsset(asset);
}

// The backend has no hard-delete endpoint, so the UI's removal action retires the asset.
export async function retireItem(id) {
  return updateItem(id, { status: "retired" });
}

export async function assignItem(id, userId) {
  return apiRequest(`/assets/${id}/assign`, {
    method: "POST",
    body: { user_id: Number(userId) },
  });
}

export async function returnItem(assetId, assignmentId) {
  let activeAssignmentId = assignmentId;
  if (!activeAssignmentId) {
    const { asset } = await apiRequest(`/assets/${assetId}`);
    activeAssignmentId = asset.current_assignment_id;
  }
  if (!activeAssignmentId) throw new Error("No active assignment was found for this asset.");
  return apiRequest(`/assignments/${activeAssignmentId}/return`, {
    method: "POST",
    body: {},
  });
}

export async function getAssignmentHistory(id) {
  const { history } = await apiRequest(`/assets/${id}/history`);
  return history.map((entry) => ({
    id: entry.assignment_id,
    userId: entry.user_id,
    assignedTo: entry.assigned_to,
    assignedAt: entry.assigned_at,
    returnedAt: entry.returned_at,
    dueBack: entry.due_back,
    returnCondition: entry.return_condition,
  }));
}