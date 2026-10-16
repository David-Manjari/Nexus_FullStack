import { Link } from "react-router-dom";

export default function UnauthorizedPage() {
  return (
    <div style={{ padding: "32px", textAlign: "center" }}>
      <h1>Access denied</h1>
      <p>You do not have permission to view this page.</p>
      <Link to="/dashboard">Return to dashboard</Link>
    </div>
  );
}
