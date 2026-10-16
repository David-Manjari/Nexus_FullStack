import { useEffect, useState } from "react";
import { decideApproval, getApprovals } from "../../api/approvals";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";
import "./Approvals.css";

function Approvals() {
  const [approvals, setApprovals] = useState([]);
  const [comments, setComments] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState(null);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setApprovals(await getApprovals());
    } catch (loadError) {
      setError(loadError.message || "Could not load approvals.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  async function updateStatus(approval, decision) {
    setBusyId(approval.id);
    setError("");
    try {
      // The backend advances the project's sequential approval chain and owns the decision state.
      await decideApproval(approval.id, decision.toLowerCase(), comments[approval.id] || "");
      await load();
    } catch (actionError) {
      setError(actionError.message || "Could not submit the approval decision.");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="approvals-page">
      <header className="approvals-header">
        <h1>Approvals</h1>
        <p>Review and manage requests awaiting approval.</p>
      </header>

      {error && <ErrorMessage message={error} onRetry={load} />}
      {loading && <Loading message="Loading approvals..." />}
      {!loading && !error && approvals.length === 0 && (
        <EmptyState title="No approvals" message="There are no pending project approvals assigned to you." />
      )}

      {!loading && !error && approvals.length > 0 && <div className="approval-list">
        {approvals.map((approval) => {
          const status = approval.status[0].toUpperCase() + approval.status.slice(1);
          const statusClass = status.toLowerCase();

          return (
            <div className="approval-card" key={approval.id}>
              <div className="approval-card-header">
                <div>
                  <h2>{approval.projectName}</h2>
                  <p>Project {approval.projectId} · round {approval.round} · step {approval.step}</p>
                </div>

                <strong className={`approval-status ${statusClass}`}>{status}</strong>
              </div>

              <div className="approval-details">
                <div>
                  <span>Submitted</span>
                  <strong>{new Date(approval.createdAt).toLocaleString()}</strong>
                </div>
                <div>
                  <span>Decision</span>
                  <strong>Pending</strong>
                </div>
              </div>

              <div className="approval-actions">
                  <input
                    type="text"
                    placeholder="Add comment (optional)"
                    value={comments[approval.id] || ""}
                    onChange={(event) =>
                      setComments({
                        ...comments,
                        [approval.id]: event.target.value,
                      })
                    }
                  />

                  <button type="button" disabled={busyId === approval.id} onClick={() => updateStatus(approval, "Approved")}>
                    Approve
                  </button>

                  <button type="button" disabled={busyId === approval.id} onClick={() => updateStatus(approval, "Rejected")}>
                    Reject
                  </button>
              </div>
            </div>
          );
        })}
      </div>}
    </div>
  );
}

export default Approvals;
