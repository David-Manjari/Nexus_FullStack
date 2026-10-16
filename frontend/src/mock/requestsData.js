// Mock data for the Requests & Procurement module (Member 4).
// Phase 2: these arrays are replaced by the Flask API.

export const REQUEST_STATUS = {
  PENDING: "pending",
  ISSUED: "issued",
  DECLINED: "declined",
  PROCUREMENT: "procurement",
};

export const PROCUREMENT_STATUS = {
  DRAFT: "draft",
  PENDING_APPROVAL: "pending_approval",
  APPROVED: "approved",
  REJECTED: "rejected",
};

export const STATUS_LABELS = {
  submitted: "Submitted",
  pending: "Waiting for store manager",
  issued: "Issued",
  declined: "Declined",
  procurement: "Sent to procurement",
  draft: "Draft",
  pending_approval: "Awaiting approval",
  approved: "Approved",
  rejected: "Rejected",
};

// Used only when mock/data.js does not export devices or vehicles yet.
export const fallbackDevices = [
  { id: "device-1", type: "device", name: "Laptop (Dell Latitude)", category: "Computer", status: "available", assignedTo: null },
  { id: "device-2", type: "device", name: "Handheld GPS", category: "Survey", status: "assigned", assignedTo: 2 },
];

export const fallbackVehicles = [
  { id: "vehicle-1", type: "vehicle", name: "Toyota Hilux KDA 123A", category: "Pickup", status: "available", assignedTo: null },
  { id: "vehicle-2", type: "vehicle", name: "Isuzu NPR KCB 456B", category: "Truck", status: "maintenance", assignedTo: null },
];

export const requests = [
  {
    id: "req-1",
    userId: 3,
    requestedBy: "Procurement Staff",
    itemId: "tool-1",
    itemName: "Cordless Drill",
    itemType: "tool",
    quantity: 1,
    reason: "Site installation at Block B",
    neededBy: "2026-10-06",
    status: "pending",
    procurementId: null,
    createdAt: "2026-10-01T09:00:00Z",
    history: [
      { status: "submitted", note: "Request submitted", by: "Procurement Staff", at: "2026-10-01T09:00:00Z" },
      { status: "pending", note: "Item available. Sent to store manager.", by: "System", at: "2026-10-01T09:00:00Z" },
    ],
  },
  {
    id: "req-2",
    userId: 3,
    requestedBy: "Procurement Staff",
    itemId: "tool-3",
    itemName: "Angle Grinder",
    itemType: "tool",
    quantity: 1,
    reason: "Cutting steel brackets for the gate",
    neededBy: "2026-10-08",
    status: "procurement",
    procurementId: "proc-1",
    createdAt: "2026-10-01T10:15:00Z",
    history: [
      { status: "submitted", note: "Request submitted", by: "Procurement Staff", at: "2026-10-01T10:15:00Z" },
      { status: "procurement", note: "Item is maintenance. Procurement request created.", by: "System", at: "2026-10-01T10:15:00Z" },
    ],
  },
];

export const procurements = [
  {
    id: "proc-1",
    requestId: "req-2",
    itemName: "Angle Grinder",
    itemType: "tool",
    quantity: 1,
    estimatedCost: null,
    supplier: "",
    notes: "Auto-created: item is maintenance",
    status: "draft",
    approvalLevel: 0,
    createdBy: "System",
    createdAt: "2026-10-01T10:15:00Z",
    history: [
      { status: "draft", note: "Created from request req-2", by: "System", at: "2026-10-01T10:15:00Z" },
    ],
  },
];
