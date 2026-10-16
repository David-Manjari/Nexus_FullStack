import React, { useEffect, useState } from "react";
import { createDisbursement, getDisbursements, processDisbursement } from "../../api/disbursements";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";
import "./Disbursements.css";

function Disbursements() {
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ payee: "", amount: "", currency: "KES", description: "" });

  async function load() {
    setLoading(true);
    setError("");
    try {
      setPayouts(await getDisbursements());
    } catch (loadError) {
      setError(loadError.message || "Could not load disbursements.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function runPayment(id, simulatedResult) {
    setBusyId(id);
    setError("");
    try {
      // The backend simulates a complete paid/failed outcome; Processing is not a client-set status.
      await processDisbursement(id, simulatedResult);
      await load();
    } catch (actionError) {
      setError(actionError.message || "Could not process this disbursement.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleCreate(event) {
    event.preventDefault();
    setCreating(true);
    setError("");
    try {
      // New payouts are created by Flask; payment outcomes remain explicitly simulated.
      await createDisbursement(form);
      setForm({ payee: "", amount: "", currency: "KES", description: "" });
      await load();
    } catch (createError) {
      setError(createError.message || "Could not create disbursement.");
    } finally {
      setCreating(false);
    }
  }

  const pending = payouts.filter(
    (payout) => payout.status === "Pending"
  );

  const completed = payouts.filter(
    (payout) => payout.status === "Paid"
  );

  const failed = payouts.filter(
    (payout) => payout.status === "Failed"
  );

  const renderPayout = (payout) => {
    const statusClass = payout.status.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="payout-card" key={payout.id}>
        <div className="payout-main">
          <div>
            <h3>{payout.recipient}</h3>
            <p>{payout.reference}</p>
          </div>

          <strong className={`payout-status ${statusClass}`}>{payout.status}</strong>
        </div>

        <div className="payout-details">
          <div>
            <span>Amount</span>
            <strong>{payout.amount}</strong>
          </div>

          <div>
            <span>Date</span>
            <strong>{payout.date}</strong>
          </div>
        </div>

        <div className="payout-actions">
          {payout.status === "Pending" && (
            <>
              <button type="button" disabled={busyId === payout.id} onClick={() => runPayment(payout.id, "paid")}>
                Simulate paid
              </button>

              <button type="button" disabled={busyId === payout.id} onClick={() => runPayment(payout.id, "failed")}>
                Simulate failed
              </button>
            </>
          )}

          {payout.status === "Paid" && <p>Payout completed successfully.</p>}
          {payout.status === "Failed" && payout.failureReason && <p>{payout.failureReason}</p>}
        </div>
      </div>
    );
  };

  return (
    <div className="disbursements-page">
      <header className="disbursements-header">
        <h1>Disbursements</h1>
        <p>Manage approved requests and monitor payout status.</p>
      </header>

      <form onSubmit={handleCreate} style={{ display: "grid", gap: 12, maxWidth: 560, marginBottom: 24 }}>
        <label>Payee<input required value={form.payee} onChange={(event) => setForm({ ...form, payee: event.target.value })} /></label>
        <label>Amount<input required type="number" min="0.01" step="0.01" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} /></label>
        <label>Currency<input required maxLength={3} value={form.currency} onChange={(event) => setForm({ ...form, currency: event.target.value })} /></label>
        <label>Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
        <button type="submit" disabled={creating}>{creating ? "Creating..." : "Create disbursement"}</button>
      </form>

      <section className="payout-queue">
        <h2>Payout Queue</h2>

        <div className="payout-counts">
          <span className="payout-count">Pending: {pending.length}</span>
          <span className="payout-count">Processing: {payouts.filter((payout) => payout.status === "Processing").length}</span>
          <span className="payout-count">Paid: {completed.length}</span>
          <span className="payout-count">Failed: {failed.length}</span>
        </div>
      </section>

      {error && <ErrorMessage message={error} onRetry={load} />}
      {loading && <Loading message="Loading disbursements..." />}
      {!loading && !error && payouts.length === 0 && (
        <EmptyState title="No disbursements" message="Disbursements created in the backend will appear here." />
      )}

      {!loading && !error && <>
      <section className="disbursements-section">
        <h2>Pending Payouts</h2>

        <div className="payout-list">
          {pending.length === 0 ? <p>No pending payouts.</p> : pending.map(renderPayout)}
        </div>
      </section>

      <section className="disbursements-section">
        <h2>Completed / Failed</h2>

        <div className="payout-list">
          {completed.length === 0 && failed.length === 0 ? (
            <p>No completed or failed payouts.</p>
          ) : (
            [...completed, ...failed].map(renderPayout)
          )}
        </div>
      </section>
      </>}
    </div>
  );
}

export default Disbursements;
