import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext"; // ASSUMPTION: returns { user }
import { getUnreadCount } from "../api/notifications";
import "./NotificationBell.css";

const POLL_MS = 30000;

export default function NotificationBell() {
  const { user } = useAuth();
  const [count, setCount] = useState(0);

  useEffect(() => {
    if (!user) return;
    let active = true;

    async function load() {
      try {
        const n = await getUnreadCount(user.id);
        if (active) setCount(n);
      } catch {
        // Keep the last known count; the bell should never crash the navbar.
      }
    }

    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [user]);

  return (
    <Link
      to="/notifications"
      className="bell"
      aria-label={`Notifications, ${count} unread`}
    >
      <span aria-hidden="true">🔔</span>
      {count > 0 && <span className="bell-badge">{count > 99 ? "99+" : count}</span>}
    </Link>
  );
}