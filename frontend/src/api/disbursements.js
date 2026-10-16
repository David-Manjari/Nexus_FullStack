import { apiRequest } from "./http";

function mapDisbursement(item) {
  const status = item.status === "success" || item.status === "paid"
    ? "Paid"
    : `${item.status[0].toUpperCase()}${item.status.slice(1)}`;
  return {
    id: item.disbursement_id,
    recipient: item.payee,
    reference: item.reference,
    amount: `${item.currency} ${Number(item.amount).toLocaleString()}`,
    date: item.created_at,
    status,
    description: item.description,
    failureReason: item.failure_reason,
  };
}

export async function getDisbursements() {
  const items = await apiRequest("/api/disbursements");
  return items.map(mapDisbursement);
}

export async function createDisbursement(fields) {
  const item = await apiRequest("/api/disbursements", {
    method: "POST",
    body: {
      payee: fields.payee,
      amount: Number(fields.amount),
      currency: fields.currency,
      description: fields.description,
    },
  });
  return mapDisbursement(item);
}

export async function processDisbursement(id, simulatedResult) {
  const { disbursement } = await apiRequest(`/api/disbursements/${id}/process`, {
    method: "POST",
    body: { simulated_result: simulatedResult },
  });
  return mapDisbursement(disbursement);
}