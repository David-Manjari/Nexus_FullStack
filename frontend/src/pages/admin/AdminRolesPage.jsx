import { ROLE_DEFINITIONS } from "../../roles";

export default function AdminRolesPage() {
  return (
    <div>
      <h1>Roles</h1>
      <p>Review the role structure and permission set used across the platform.</p>

      <div style={{ display: "grid", gap: "12px", marginTop: "20px" }}>
        {ROLE_DEFINITIONS.map((role) => (
          <div key={role.key} style={{ border: "1px solid var(--color-border)", borderRadius: "12px", padding: "16px", background: "var(--color-surface)", boxShadow: "0 6px 16px rgba(32, 52, 45, 0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center", marginBottom: "8px" }}>
              <strong>{role.label}</strong>
              <span style={{ background: "var(--color-surface-muted)", color: "var(--color-ink)", padding: "6px 10px", borderRadius: "999px", fontSize: "0.8rem" }}>
                {role.key}
              </span>
            </div>
            <p style={{ margin: "0 0 12px", color: "var(--color-muted)" }}>{role.description}</p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {role.permissions.map((permission) => (
                <span key={permission} style={{ background: "var(--color-primary-soft)", color: "var(--color-primary)", padding: "6px 10px", borderRadius: "999px", fontSize: "0.8rem" }}>
                  {permission}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
