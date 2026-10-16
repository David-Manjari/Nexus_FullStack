import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { escalateProcurement, getProcurements } from "../../api/procurement";
import { EmptyState, ErrorState, LoadingState } from "../requests/ModuleStates";
import RequestTimeline from "../requests/RequestTimeline";
import StatusPill from "../requests/StatusPill";
import "../requests/Requests.css";

const formatKes = (value) => (value ? `KES ${Number(value).toLocaleString()}` : "Not set");

export default function ProcurementQueue() {
  const { user } = useAuth();
  const canCreate = user?.role === "admin" || user?.role === "store_manager";
  const [procurements, setProcurements] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [openId, setOpenId] = useState(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setProcurements(await getProcurements());
    } catch (err) {
      setError(err.message || "Could not load the procurement queue.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function sendToApprover(id) {
    setBusyId(id);
    setActionError("");
    try {
      await escalateProcurement(id, user);
      await load();
    } catch (err) {
      setActionError(err.message || "Could not send this request.");
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <LoadingState text="Loading procurement queue..." />;
  if (error) return <ErrorState message={error} onRetry={load} />;

  return (
    <section className="rq-page">
      <header className="rq-header">
        <h2>Procurement queue</h2>
        {canCreate && <Link className="rq-btn" to="/procurement/new">New procurement</Link>}
      </header>

      {actionError && <div className="rq-banner rq-banner--error">{actionError}</div>}

      {procurements.length === 0 ? (
        <EmptyState text="No procurement requests yet.">
          <Link className="rq-btn" to="/procurement/new">Create one</Link>
        </EmptyState>
      ) : (
        <ul className="rq-list">
          {procurements.map((procurement) => {
            const incomplete = !procurement.estimatedCost || !procurement.supplier;
            return (
              <li key={procurement.id} className="rq-card">
                <div className="rq-card__top">
                  <div>
                    <h3>{procurement.itemName}</h3>
                    <p className="rq-meta">
                      {procurement.quantity} × {procurement.itemType} · {formatKes(procurement.estimatedCost)} · {procurement.supplier || "No supplier"}
                      {procurement.approvalLevel > 0 && ` · level ${procurement.approvalLevel}`}
                    </p>
                  </div>
                  <StatusPill status={procurement.status} />
                </div>
                {procurement.notes && <p className="rq-reason">{procurement.notes}</p>}

                {procurement.status === "draft" && (
                  <div className="rq-actions">
                    <Link className="rq-btn rq-btn--ghost" to={`/procurement/new?edit=${procurement.id}`}>
                      {incomplete ? "Add cost & supplier" : "Edit"}
                    </Link>
                    <button
                      className="rq-btn"
                      disabled={incomplete || busyId === procurement.id}
                      title={incomplete ? "Add an estimated cost and supplier first" : ""}
                      onClick={() => sendToApprover(procurement.id)}
                    >
                      Send to approver
                    </button>
                  </div>
                )}

                <button
                  className="rq-link"
                  onClick={() => setOpenId(openId === procurement.id ? null : procurement.id)}
                  aria-expanded={openId === procurement.id}
                >
                  {openId === procurement.id ? "Hide timeline" : "Show timeline"}
                </button>
                {openId === procurement.id && <RequestTimeline history={procurement.history} />}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
