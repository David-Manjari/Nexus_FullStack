import { useEffect, useState } from "react";
import { useAuth } from "../../auth/AuthContext";
import { createUser, deactivateUser, getUsers, updateUser } from "../../api/users";
import { getRoleLabel, ROLE_DEFINITIONS } from "../../roles";
import Loading from "../../components/Loading";
import ErrorMessage from "../../components/ErrorMessage";
import EmptyState from "../../components/EmptyState";
import "./AdminUsersPage.css";

export default function AdminUsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ username: "", email: "", password: "", role: "staff" });
  const [createFormOpen, setCreateFormOpen] = useState(false);
  const [editingUserId, setEditingUserId] = useState(null);
  const [editForm, setEditForm] = useState({ username: "", email: "", password: "", role: "staff" });
  const [editError, setEditError] = useState("");
  const [updating, setUpdating] = useState(false);

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
      setCreateFormOpen(false);
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

  function startEditing(member) {
    setEditingUserId(member.id);
    setEditForm({
      username: member.name,
      email: member.email,
      password: "",
      role: member.role,
    });
    setEditError("");
  }

  function cancelEditing() {
    setEditingUserId(null);
    setEditError("");
    setEditForm({ username: "", email: "", password: "", role: "staff" });
  }

  async function handleUpdate(event) {
    event.preventDefault();
    setUpdating(true);
    setEditError("");
    const changes = {
      username: editForm.username,
      email: editForm.email,
    };
    const editingMember = users.find((member) => member.id === editingUserId);
    if (editingMember?.role !== "admin") changes.role = editForm.role;
    if (editForm.password) changes.password = editForm.password;

    try {
      await updateUser(editingUserId, changes);
      cancelEditing();
      await loadUsers();
    } catch (updateError) {
      setEditError(updateError.message || "Could not update account.");
    } finally {
      setUpdating(false);
    }
  }

  return (
    <div className="admin-users-page">
      <header className="admin-users-header">
        <div>
          <h1>Users</h1>
          <p>Manage user access and review current identities in the workspace.</p>
        </div>
        <button
          type="button"
          aria-expanded={createFormOpen}
          aria-controls="create-account-form"
          onClick={() => setCreateFormOpen((open) => !open)}
        >
          {createFormOpen ? "Cancel" : "Create account"}
        </button>
      </header>

      {error && <ErrorMessage message={error} onRetry={loadUsers} />}
      {createFormOpen && <form id="create-account-form" className="admin-users-form" onSubmit={handleCreate}>
        <label>Username<input required minLength={3} maxLength={64} value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} /></label>
        <label>Email<input required type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
        <label>
          Password
          <input
            required
            minLength={8}
            pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9\s]).{8,}"
            title="Use at least 8 characters with uppercase and lowercase letters, a number, and a special character."
            autoComplete="new-password"
            type="password"
            value={form.password}
            onChange={(event) => setForm({ ...form, password: event.target.value })}
          />
          <small>At least 8 characters with uppercase and lowercase letters, a number, and a special character.</small>
        </label>
        <label>Role<select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
          {ROLE_DEFINITIONS.map((role) => <option key={role.key} value={role.key}>{role.label}</option>)}
        </select></label>
        <button type="submit" disabled={saving}>{saving ? "Creating..." : "Create account"}</button>
      </form>}

      {loading && <Loading message="Loading users..." />}
      {!loading && !error && users.length === 0 && (
        <EmptyState title="No users" message="There are no user accounts to display." />
      )}

      <div style={{ display: "grid", gap: "12px", marginTop: "20px" }}>
        {!loading && !error && users.map((member) => (
          <div key={member.id} style={{ border: "1px solid var(--color-border)", borderRadius: "12px", padding: "16px", background: "var(--color-surface)", boxShadow: "0 6px 16px rgba(32, 52, 45, 0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center" }}>
              <div>
                <strong>{member.name}</strong>
                <div style={{ color: "var(--color-muted)" }}>{member.email}</div>
              </div>
              <span style={{
                background: member.id === user.id ? "var(--color-primary-soft)" : "var(--color-surface-muted)",
                color: member.id === user.id ? "var(--color-primary)" : "var(--color-ink)",
                padding: "6px 10px",
                borderRadius: "999px",
                fontSize: "0.8rem",
                fontWeight: 700,
              }}>
                {member.active ? "Active" : "Inactive"}
              </span>
            </div>

            <div style={{ marginTop: "12px", display: "flex", gap: "12px", flexWrap: "wrap" }}>
              <span style={{ background: "var(--color-primary-soft)", color: "var(--color-primary)", padding: "6px 10px", borderRadius: "999px" }}>
                {getRoleLabel(member.role)}
              </span>
              <span style={{ background: "var(--color-surface-muted)", color: "var(--color-ink)", padding: "6px 10px", borderRadius: "999px" }}>
                {member.id === user.id ? "Signed-in user" : "Account"}
              </span>
            </div>
            {editingUserId !== null && editingUserId === member.id ? (
              <form
                onSubmit={handleUpdate}
                style={{ display: "grid", gap: 12, maxWidth: 560, marginTop: 16 }}
              >
                <label>
                  Username
                  <input
                    required
                    minLength={3}
                    maxLength={64}
                    value={editForm.username}
                    onChange={(event) => setEditForm({ ...editForm, username: event.target.value })}
                  />
                </label>
                <label>
                  Email
                  <input
                    required
                    type="email"
                    value={editForm.email}
                    onChange={(event) => setEditForm({ ...editForm, email: event.target.value })}
                  />
                </label>
                <label>
                  New password
                  <input
                    type="password"
                    minLength={8}
                    pattern="(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9\s]).{8,}"
                    autoComplete="new-password"
                    title="Use at least 8 characters with uppercase and lowercase letters, a number, and a special character."
                    value={editForm.password}
                    onChange={(event) => setEditForm({ ...editForm, password: event.target.value })}
                    placeholder="Leave blank to keep the current password"
                  />
                  <small>When changing it, use at least 8 characters with uppercase and lowercase letters, a number, and a special character.</small>
                </label>
                <label>
                  Role
                  <select
                    value={editForm.role}
                    disabled={member.role === "admin"}
                    onChange={(event) => setEditForm({ ...editForm, role: event.target.value })}
                  >
                    {ROLE_DEFINITIONS.map((role) => (
                      <option key={role.key} value={role.key}>{role.label}</option>
                    ))}
                  </select>
                </label>
                {member.role === "admin" && (
                  <p style={{ margin: "-6px 0 0", color: "var(--color-muted)" }}>
                    Admin account roles cannot be changed.
                  </p>
                )}
                {editError && <p role="alert" style={{ color: "#b91c1c", margin: 0 }}>{editError}</p>}
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                  <button type="submit" disabled={updating}>
                    {updating ? "Saving..." : "Save changes"}
                  </button>
                  <button type="button" disabled={updating} onClick={cancelEditing}>
                    Cancel
                  </button>
                </div>
              </form>
            ) : (
              <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                <button type="button" onClick={() => startEditing(member)}>
                  Edit account
                </button>
                {member.id !== user.id && (
                  <button type="button" onClick={() => toggleActive(member)}>
                    {member.active ? "Deactivate" : "Reactivate"}
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
