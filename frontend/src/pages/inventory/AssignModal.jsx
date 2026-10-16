import { useState } from "react";
import { assignItem } from "../../api/inventory";
import InventoryModal from "./InventoryModal";

export default function AssignModal({ item, users, onClose, onSaved }) {
  const [userId, setUserId] = useState("");
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!userId) {
      setError("Choose a user");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const user = users.find((u) => String(u.id) === userId);
      await assignItem(item.id, user.id);
      onSaved();
    } catch (err) {
      setError(err.message);
      setSaving(false);
    }
  }

  return (
    <InventoryModal title={`Assign ${item.name}`} onClose={onClose}>
      <form className="inv-form" onSubmit={handleSubmit}>
        <label>
          Assign to
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            <option value="">Select a user</option>
            {users.map((u) => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>
        </label>
        {error && <p className="inventory-error">{error}</p>}
        <div className="inv-form-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button type="submit" disabled={saving}>{saving ? "Assigning..." : "Assign"}</button>
        </div>
      </form>
    </InventoryModal>
  );
}