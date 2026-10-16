import { useEffect, useState } from "react";
import { getAssignmentHistory } from "../../api/inventory";
import InventoryModal from "./InventoryModal";

const formatDate = (iso) => new Date(iso).toLocaleString();

export default function HistoryModal({ item, users, onClose }) {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getAssignmentHistory(item.id).then(setHistory).catch((err) => setError(err.message));
  }, [item.id]);

  const userName = (id) => users.find((u) => u.id === id)?.name ?? "Unknown user";

  return (
    <InventoryModal title={`History: ${item.name}`} onClose={onClose}>
      {error && <p className="inventory-error">{error}</p>}
      {!history && !error && <p className="inventory-state">Loading history...</p>}
      {history?.length === 0 && <p className="inventory-state">Never assigned.</p>}
      {history?.length > 0 && (
        <ul className="history-list">
          {history.map((h) => (
            <li key={h.id}>
              {userName(h.userId)}: {formatDate(h.assignedAt)} to{" "}
              {h.returnedAt ? formatDate(h.returnedAt) : "still out"}
            </li>
          ))}
        </ul>
      )}
      <div className="inv-form-actions">
        <button onClick={onClose}>Close</button>
      </div>
    </InventoryModal>
  );
}