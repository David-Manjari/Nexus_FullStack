import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext"; // ASSUMPTION: returns { user }
import { getNotifications, markAsRead, markAllAsRead } from "../../api/notifications";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";
import "./NotificationsPage.css";

export default function NotificationsPage() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setItems([...(await getNotifications(user.id))]);
    } catch {
      setError("Could not load your notifications.");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { load(); }, [load]);

  async function handleRead(id) {
    try {
      await markAsRead(id);
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read: true } : n)));
    } catch {
      setError("Could not update that notification.");
    }
  }

  async function handleReadAll() {
    try {
      await markAllAsRead(user.id);
      setItems((prev) => prev.map((n) => ({ ...n, read: true })));
    } catch {
      setError("Could not update your notifications.");
    }
  }

  if (loading) return <Loading message="Loading notifications..." />;
  if (error) return <ErrorMessage message={error} onRetry={load} />;
  if (items.length === 0)
    return <EmptyState title="No notifications" message="Assignments and escalations will show up here." />;

  const unread = items.filter((n) => !n.read).length;

  return (
    <section className="notif-page">
      <header className="notif-header">
        <h1>Notifications</h1>
        <button type="button" onClick={handleReadAll} disabled={unread === 0}>
          Mark all as read
        </button>
      </header>
      <ul className="notif-list">
        {items.map((n) => (
          <li key={n.id} className={n.read ? "notif" : "notif notif-unread"}>
            <div>
              <p className="notif-message">{n.message}</p>
              <p className="notif-meta">
                {new Date(n.createdAt).toLocaleString()}
                {n.emailSent && " · email sent"}
              </p>
            </div>
            {!n.read && (
              <button type="button" onClick={() => handleRead(n.id)}>Mark as read</button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}