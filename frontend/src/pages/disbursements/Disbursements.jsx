import React, { useEffect, useState } from "react";
import { createDisbursement, getDisbursements, processDisbursement } from "../../api/disbursements";
import { useAuth } from "../../auth/AuthContext";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";
import "./Disbursements.css";

function Disbursements() {
  const { user } = useAuth();
  const isStaff = user?.role === "staff";
  const [payouts, setPayouts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [creating, setCreating] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("All");
  const [form, setForm] = useState({
    payee: "",
    recipientPhone: "",
    amount: "",
    currency: "KES",
    description: "",
  });

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

  const hasProcessing = payouts.some((payout) => payout.status === "Processing");
  useEffect(() => {
    if (!hasProcessing) return undefined;

    let active = true;
    const interval = window.setInterval(async () => {
      try {
        const latest = await getDisbursements();
        if (active) {
          setPayouts(latest);
          setError("");
        }
      } catch (refreshError) {
        if (active) {
          setError(refreshError.message || "Could not refresh payout status.");
        }
      }
    }, 8000);

    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [hasProcessing]);

  async function runPayment(id) {
    setBusyId(id);
    setError("");
    try {
      await processDisbursement(id);
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
      await createDisbursement(form);
      setForm({
        payee: "",
        recipientPhone: "",
        amount: "",
        currency: "KES",
        description: "",
      });
      setFormOpen(false);
      await load();
    } catch (createError) {
      setError(createError.message || "Could not create disbursement.");
    } finally {
      setCreating(false);
    }
  }

  const filteredPayouts = payouts
    .filter((payout) => statusFilter === "All" || payout.status === statusFilter)
    .sort((first, second) => Date.parse(second.updatedAt) - Date.parse(first.updatedAt));
  const pendingCount = payouts.filter((payout) => payout.status === "Pending").length;
  const processingCount = payouts.filter((payout) => payout.status === "Processing").length;
  const paidCount = payouts.filter((payout) => payout.status === "Paid").length;
  const failedCount = payouts.filter((payout) => payout.status === "Failed").length;

  const renderPayout = (payout) => {
    let displayStatus = payout.status;
    let statusClass = payout.status.toLowerCase().replace(/\s+/g, "-");
    if (payout.approvalStatus === "pending") {
      displayStatus = "Awaiting approval";
      statusClass = "pending";
    } else if (payout.approvalStatus === "rejected") {
      displayStatus = "Request declined";
      statusClass = "failed";
    } else if (
      payout.approvalStatus === "approved"
      && payout.status === "Pending"
    ) {
      displayStatus = "Approved - awaiting payment";
      statusClass = "pending";
    }

    return (
      <div className="payout-card" key={payout.id}>
        <div className="payout-main">
          <div>
            <h3>{payout.recipient}</h3>
            <p>{payout.reference}</p>
            {payout.recipientPhone && <p>Mobile: {payout.recipientPhone}</p>}
          </div>

          <strong className={`payout-status ${statusClass}`}>{displayStatus}</strong>
        </div>

        {payout.approvalStatus && (
          <p className="payout-approval-status">
            Approval: {payout.approvalStatus}
          </p>
        )}
        {isStaff && payout.approvalStatus === "rejected" && payout.approvalReason && (
          <p className="payout-approval-status">{payout.approvalReason}</p>
        )}

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
          {!isStaff && payout.status === "Pending" && payout.approvalStatus === "approved" && (
            <button type="button" disabled={busyId === payout.id} onClick={() => runPayment(payout.id)}>
              {busyId === payout.id ? "Submitting..." : "Pay"}
            </button>
          )}

          {payout.status === "Processing" && (
            <p>{payout.providerMessage || "Awaiting Daraja callback. Do not retry while processing."}</p>
          )}
          {payout.status === "Paid" && <p>Sandbox payout completed successfully.</p>}
          {payout.status === "Failed" && payout.failureReason && <p>{payout.failureReason}</p>}
        </div>
      </div>
    );
  };

  return (
    <div className="disbursements-page">
      <header className="disbursements-header">
        <h1>{isStaff ? "My Disbursement Requests" : "Disbursements"}</h1>
        <p>
          {isStaff
            ? "Submit requests and follow their approval and payment progress."
            : "Sandbox only: no production payouts are sent."}
        </p>
        <button
          className="disbursement-form-toggle"
          type="button"
          aria-expanded={formOpen}
          aria-controls="disbursement-form"
          onClick={() => setFormOpen((open) => !open)}
        >
          {formOpen ? "Cancel new disbursement" : "Create disbursement"}
        </button>
      </header>

      {formOpen && (
        <form id="disbursement-form" className="disbursement-form" onSubmit={handleCreate}>
          <label>Payee<input required value={form.payee} onChange={(event) => setForm({ ...form, payee: event.target.value })} /></label>
          <label>Safaricom mobile number<input required type="tel" placeholder="07XXXXXXXX" value={form.recipientPhone} onChange={(event) => setForm({ ...form, recipientPhone: event.target.value })} /></label>
          <label>Amount (KES)<input required type="number" min="1" max="70000" step="1" value={form.amount} onChange={(event) => setForm({ ...form, amount: event.target.value })} /></label>
          <label>Description<textarea value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
          <button type="submit" disabled={creating}>{creating ? "Creating..." : "Save disbursement"}</button>
        </form>
      )}

      <section className="payout-queue">
        <h2>Payout Queue</h2>

        <div className="payout-counts">
          <span className="payout-count">Pending: {pendingCount}</span>
          <span className="payout-count">Processing: {processingCount}</span>
          <span className="payout-count">Paid: {paidCount}</span>
          <span className="payout-count">Failed: {failedCount}</span>
        </div>
      </section>

      {error && <ErrorMessage message={error} onRetry={load} />}
      {loading && <Loading message="Loading disbursements..." />}
      {!loading && !error && payouts.length === 0 && (
        <EmptyState
          title={isStaff ? "No disbursement requests" : "No disbursements"}
          message={isStaff
            ? "Requests you submit will appear here so you can follow their progress."
            : "Disbursements created in the backend will appear here."}
        />
      )}

      {!loading && !error && payouts.length > 0 && (
        <section className="disbursements-section">
          <div className="payout-section-heading">
            <h2>{isStaff ? "My Disbursements" : "All Disbursements"}</h2>
            <label className="payout-status-filter">
              <span>Status</span>
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                <option value="All">All statuses</option>
                <option value="Pending">Pending</option>
                <option value="Processing">Processing</option>
                <option value="Paid">Paid</option>
                <option value="Failed">Failed</option>
              </select>
            </label>
          </div>
          <div className="payout-list">
            {filteredPayouts.length === 0
              ? <p>No {statusFilter.toLowerCase()} disbursements found.</p>
              : filteredPayouts.map(renderPayout)}
          </div>
        </section>
      )}
    </div>
  );
}

export default Disbursements;
