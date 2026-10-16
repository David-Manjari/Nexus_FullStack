import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { createRequest, getRequestableItems } from "../../api/requests";
import { ErrorState, LoadingState } from "./ModuleStates";
import "./Requests.css";

const TYPES = [
  { value: "tool", label: "Tool" },
  { value: "device", label: "Device" },
  { value: "vehicle", label: "Vehicle" },
];

const EMPTY_FORM = { type: "tool", itemId: "", quantity: 1, reason: "", neededBy: "" };
const today = () => new Date().toISOString().slice(0, 10);

function validate(form) {
  const errors = {};
  const quantity = Number(form.quantity);
  if (!form.itemId) errors.itemId = "Choose an item.";
  if (!Number.isInteger(quantity) || quantity < 1) errors.quantity = "Enter a whole number of at least 1.";
  if (form.reason.trim().length < 5) errors.reason = "Give a short reason (at least 5 characters).";
  if (!form.neededBy) errors.neededBy = "Pick the date you need it by.";
  else if (form.neededBy < today()) errors.neededBy = "The date cannot be in the past.";
  return errors;
}

export default function RequestForm() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const [result, setResult] = useState(null);

  async function loadItems() {
    setLoading(true);
    setLoadError("");
    try {
      setItems(await getRequestableItems());
    } catch (error) {
      setLoadError(error.message || "Could not load items.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadItems();
  }, []);

  const options = items.filter((item) => item.type === form.type);
  const selected = items.find((item) => item.id === form.itemId);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value, ...(field === "type" ? { itemId: "" } : {}) }));
    setErrors((current) => ({ ...current, [field]: undefined }));
    setResult(null);
    setSubmitError("");
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const found = validate(form);
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    setSubmitError("");
    try {
      const created = await createRequest(form, user);
      setResult(created);
      setForm(EMPTY_FORM);
      setItems(await getRequestableItems());
    } catch (error) {
      setSubmitError(error.message || "Could not submit the request.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <LoadingState text="Loading items..." />;
  if (loadError) return <ErrorState message={loadError} onRetry={loadItems} />;

  return (
    <section className="rq-page">
      <header className="rq-header">
        <h2>Request a tool, device or vehicle</h2>
        <Link className="rq-btn rq-btn--ghost" to="/requests">My requests</Link>
      </header>

      {result && (
        <div className={`rq-banner ${result.status === "procurement" ? "rq-banner--warn" : "rq-banner--ok"}`}>
          {result.status === "procurement"
            ? `${result.itemName} is not available right now, so a procurement request was raised for you.`
            : `Request for ${result.itemName} sent to the store manager.`}{" "}
          <Link to="/requests">View my requests</Link>
        </div>
      )}
      {submitError && <div className="rq-banner rq-banner--error">{submitError}</div>}

      <form className="rq-card rq-form" onSubmit={handleSubmit} noValidate>
        <div className="rq-field">
          <span className="rq-label">Type</span>
          <div className="rq-segment">
            {TYPES.map((type) => (
              <button
                type="button"
                key={type.value}
                className={form.type === type.value ? "is-active" : ""}
                onClick={() => update("type", type.value)}
              >
                {type.label}
              </button>
            ))}
          </div>
        </div>

        <label className="rq-field">
          <span className="rq-label">Item</span>
          <select value={form.itemId} onChange={(e) => update("itemId", e.target.value)}>
            <option value="">Select an item</option>
            {options.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({item.status})
              </option>
            ))}
          </select>
          {options.length === 0 && <small className="rq-hint">No items of this type yet.</small>}
          {errors.itemId && <small className="rq-error">{errors.itemId}</small>}
        </label>

        {selected && (
          <p className={`rq-availability ${selected.status === "available" ? "is-available" : "is-unavailable"}`}>
            {selected.status === "available"
              ? "Available. Your request will go to the store manager."
              : `Unavailable (${selected.status}). Submitting will raise a procurement request.`}
          </p>
        )}

        <div className="rq-row">
          <label className="rq-field">
            <span className="rq-label">Quantity</span>
            <input type="number" min="1" value={form.quantity} onChange={(e) => update("quantity", e.target.value)} />
            {errors.quantity && <small className="rq-error">{errors.quantity}</small>}
          </label>

          <label className="rq-field">
            <span className="rq-label">Needed by</span>
            <input type="date" min={today()} value={form.neededBy} onChange={(e) => update("neededBy", e.target.value)} />
            {errors.neededBy && <small className="rq-error">{errors.neededBy}</small>}
          </label>
        </div>

        <label className="rq-field">
          <span className="rq-label">Reason</span>
          <textarea rows="3" value={form.reason} onChange={(e) => update("reason", e.target.value)} placeholder="What is it for?" />
          {errors.reason && <small className="rq-error">{errors.reason}</small>}
        </label>

        <button className="rq-btn" type="submit" disabled={submitting}>
          {submitting ? "Submitting..." : "Submit request"}
        </button>
      </form>
    </section>
  );
}
