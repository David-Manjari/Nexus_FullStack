import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { createUser, deactivateUser, getUsers, updateUser } from "../../api/users";
import { getRoleLabel, ROLE_DEFINITIONS } from "../../roles";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";

export default function AdminUsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "", role: "staff" });

  async function loadUsers() {
    setLoading(true);
    setError(null);
    try {
      setUsers(await getUsers());
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadUsers();
  }, []);

  async function handleCreate(event) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      // Account creation now uses the backend's validated role and password rules.
      await createUser(form);
      setForm({ username: "", email: "", password: "", role: "staff" });
      await loadUsers();
    } catch (createError) {
      setError(createError.message || "Could not create account.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(member) {
    setError(null);
    try {
      if (member.active) await deactivateUser(member.id);
      else await updateUser(member.id, { is_active: true });
      await loadUsers();
    } catch (updateError) {
      setError(updateError.message || "Could not update account.");
    }
  }

  return (
    <div>
      <h1>Users</h1>
      <p>Manage user access and review current identities in the workspace.</p>

      {error && <ErrorMessage message={error} onRetry={loadUsers} />}
      <form onSubmit={handleCreate} style={{ display: "grid", gap: 12, maxWidth: 560, margin: "20px 0" }}>
        <label>Username<input required minLength={3} maxLength={64} value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
        <label>Email<input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
        <label>Password<input required minLength={6} type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} /></label>
        <label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
          {ROLE_DEFINITIONS.map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}
        </select></label>
        <button type="submit" disabled={saving}>{saving ? "Creating..." : "Create account"}</button>
      </form>

      {loading && <Loading message="Loading users..." />}
      {!loading && !error && users.length === 0 && (
        <EmptyState title="No users" message="There are no user accounts to display." />
      )}

      <div style={{ display: "grid", gap: "12px", marginTop: "20px" }}>
        {!loading && !error && users.map((member) => (
          <div key={member.id} style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "16px", background: "#fff" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center" }}>
              <div>
                <strong>{member.name}</strong>
                <div style={{ color: "#475569" }}>{member.email}</div>
              </div>
              <span style={{
                background: member.id === user.id ? "#dbeafe" : "#e2e8f0",
                color: member.id === user.id ? "#1d4ed8" : "#334155",
                padding: "6px 10px",
                borderRadius: "999px",
                fontSize: "0.8rem",
                fontWeight: 700,
              }}>
                {member.active ? "Active" : "Inactive"}
              </span>
            </div>

            <div style={{ marginTop: "12px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <span style={{ background: "#eef2ff", color: "#4338ca", padding: "6px 10px", borderRadius: "999px" }}>
                {getRoleLabel(member.role)}
              </span>
              <span style={{ background: "#f1f5f9", color: "#334155", padding: "6px 10px", borderRadius: "999px" }}>
                {member.id === user.id ? "Signed-in user" : "Account"}
              </span>
            </div>
            {member.id !== user.id && (
              <button type="button" onClick={() => toggleActive(member)}>
                {member.active ? "Deactivate" : "Reactivate"}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
