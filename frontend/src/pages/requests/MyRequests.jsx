import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { getMyRequests } from "../../api/requests";
import { EmptyState, ErrorState, LoadingState } from "./ModuleStates";
import RequestTimeline from "./RequestTimeline";
import StatusPill from "./StatusPill";
import "./Requests.css";

export default function MyRequests() {
  const { user } = useAuth();
  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [openId, setOpenId] = useState(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setRequests(await getMyRequests(user.id));
    } catch (err) {
      setError(err.message || "Could not load your requests.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (user) load();
  }, [user]);

  return (
    <section className="rq-page">
      <header className="rq-header">
        <h2>My requests</h2>
        <Link className="rq-btn" to="/requests/new">New request</Link>
      </header>

      {loading && <LoadingState text="Loading your requests..." />}
      {!loading && error && <ErrorState message={error} onRetry={load} />}
      {!loading && !error && requests.length === 0 && (
        <EmptyState text="You have not made any requests yet.">
          <Link className="rq-btn" to="/requests/new">Make your first request</Link>
        </EmptyState>
      )}

      {!loading && !error && requests.length > 0 && (
        <ul className="rq-list">
          {requests.map((request) => (
            <li key={request.id} className="rq-card">
              <div className="rq-card__top">
                <div>
                  <h3>{request.itemName}</h3>
                  <p className="rq-meta">
                    {request.quantity} × {request.itemType} · needed by {request.neededBy}
                  </p>
                </div>
                <StatusPill status={request.status} />
              </div>
              <p className="rq-reason">{request.reason}</p>
              <button
                className="rq-link"
                onClick={() => setOpenId(openId === request.id ? null : request.id)}
                aria-expanded={openId === request.id}
              >
                {openId === request.id ? "Hide timeline" : "Show timeline"}
              </button>
              {openId === request.id && <RequestTimeline history={request.history} />}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
