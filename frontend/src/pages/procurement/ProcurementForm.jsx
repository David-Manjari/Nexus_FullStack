import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { createProcurement, getProcurementById, updateProcurement } from "../../api/procurement";
import { ErrorState, LoadingState } from "../requests/ModuleStates";
import "../requests/Requests.css";

const EMPTY_FORM = { itemName: "", itemType: "tool", quantity: 1, estimatedCost: "", supplier: "", notes: "" };

function validate(form) {
  const errors = {};
  const quantity = Number(form.quantity);
  const cost = Number(form.estimatedCost);
  if (!form.itemName.trim()) errors.itemName = "Enter the item name.";
  if (!Number.isInteger(quantity) || quantity < 1) errors.quantity = "Enter a whole number of at least 1.";
  if (form.estimatedCost === "" || !(cost > 0)) errors.estimatedCost = "Enter an estimated cost above 0.";
  if (!form.supplier.trim()) errors.supplier = "Enter a supplier.";
  return errors;
}

export default function ProcurementForm() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const editId = params.get("edit");

  const [form, setForm] = useState(EMPTY_FORM);
  const [linkedRequest, setLinkedRequest] = useState(null);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(Boolean(editId));
  const [loadError, setLoadError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");

  async function loadExisting() {
    setLoading(true);
    setLoadError("");
    try {
      const existing = await getProcurementById(editId);
      if (existing.status !== "draft") throw new Error("Only drafts can be edited.");
      setLinkedRequest(existing.requestId);
      setForm({
        itemName: existing.itemName,
        itemType: existing.itemType,
        quantity: existing.quantity,
        estimatedCost: existing.estimatedCost ?? "",
        supplier: existing.supplier,
        notes: existing.notes,
      });
    } catch (error) {
      setLoadError(error.message || "Could not load this procurement request.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (editId) loadExisting();
  }, [editId]);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    setSaveError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSaving(true);
    setSaveError("");
    try {
      if (editId) await updateProcurement(editId, form, user);
      else await createProcurement(form, user);
      navigate("/procurement");
    } catch (error) {
      setSaveError(error.message || "Could not save.");
      setSaving(false);
    }
  }

  if (loading) return <LoadingState />;
  if (loadError) return <ErrorState message={loadError} onRetry={loadExisting} />;

  return (
    <section className="rq-page">
      <header className="rq-header">
        <h2>{editId ? "Complete procurement request" : "New procurement request"}</h2>
        <Link className="rq-btn rq-btn--ghost" to="/procurement">Back to queue</Link>
      </header>

      {linkedRequest && (
        <div className="rq-banner rq-banner--warn">
          Raised automatically from request {linkedRequest}. Add the cost and supplier, then send it for approval.
        </div>
      )}
      {saveError && <div className="rq-banner rq-banner--error">{saveError}</div>}

      <form className="rq-card rq-form" onSubmit={handleSubmit} noValidate>
        <div className="rq-row">
          <label className="rq-field">
            <span className="rq-label">Item</span>
            <input value={form.itemName} onChange={(e) => update("itemName", e.target.value)} />
            {errors.itemName && <small className="rq-error">{errors.itemName}</small>}
          </label>
          <label className="rq-field">
            <span className="rq-label">Type</span>
            <select value={form.itemType} onChange={(e) => update("itemType", e.target.value)}>
              <option value="tool">Tool</option>
              <option value="device">Device</option>
              <option value="vehicle">Vehicle</option>
            </select>
          </label>
        </div>

        <div className="rq-row">
          <label className="rq-field">
            <span className="rq-label">Quantity</span>
            <input type="number" min="1" value={form.quantity} onChange={(e) => update("quantity", e.target.value)} />
            {errors.quantity && <small className="rq-error">{errors.quantity}</small>}
          </label>
          <label className="rq-field">
            <span className="rq-label">Estimated cost (KES)</span>
            <input type="number" min="1" value={form.estimatedCost} onChange={(e) => update("estimatedCost", e.target.value)} />
            {errors.estimatedCost && <small className="rq-error">{errors.estimatedCost}</small>}
          </label>
        </div>

        <label className="rq-field">
          <span className="rq-label">Supplier</span>
          <input value={form.supplier} onChange={(e) => update("supplier", e.target.value)} />
          {errors.supplier && <small className="rq-error">{errors.supplier}</small>}
        </label>

        <label className="rq-field">
          <span className="rq-label">Notes</span>
          <textarea rows="3" value={form.notes} onChange={(e) => update("notes", e.target.value)} />
        </label>

        <button className="rq-btn" type="submit" disabled={saving}>
          {saving ? "Saving..." : editId ? "Save changes" : "Create request"}
        </button>
      </form>
    </section>
  );
}
