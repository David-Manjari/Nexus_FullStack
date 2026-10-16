import { ROLE_DEFINITIONS } from "../../roles";

export default function AdminRolesPage() {
  return (
    <div>
      <h1>Roles</h1>
      <p>Review the role structure and permission set used across the platform.</p>

      <div style={{ display: "grid", gap: "12px", marginTop: "20px" }}>
        {ROLE_DEFINITIONS.map((role) => (
          <div key={role.key} style={{ border: "1px solid #e5e7eb", borderRadius: "12px", padding: "16px", background: "#fff" }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "center", marginBottom: "8px" }}>
              <strong>{role.label}</strong>
              <span style={{ background: "#f1f5f9", color: "#334155", padding: "6px 10px", borderRadius: "999px", fontSize: "0.8rem" }}>
                {role.key}
              </span>
            </div>
            <p style={{ margin: "0 0 12px", color: "#475569" }}>{role.description}</p>
            <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
              {role.permissions.map((permission) => (
                <span key={permission} style={{ background: "#ecfeff", color: "#0f766e", padding: "6px 10px", borderRadius: "999px", fontSize: "0.8rem" }}>
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
