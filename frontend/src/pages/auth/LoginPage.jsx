import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { ROLE_DEFINITIONS } from "../../roles";

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, user } = useAuth();
  const [form, setForm] = useState({
    email: "",
    password: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (user) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleChange = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);

    try {
      // Let Flask validate credentials and provide the session cookie.
      await login(form);
      navigate("/dashboard", { replace: true });
    } catch (submitError) {
      setError(submitError.message || "Unable to log in.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "linear-gradient(135deg, #0f172a, #111827)",
      padding: "24px",
      color: "#e5e7eb",
      fontFamily: "Arial, sans-serif",
    }}>
      <div style={{
        width: "100%",
        maxWidth: "980px",
        display: "grid",
        gridTemplateColumns: "1.1fr 0.9fr",
        gap: "24px",
      }}>
        <section style={{
          background: "rgba(15, 23, 42, 0.72)",
          border: "1px solid rgba(148, 163, 184, 0.25)",
          borderRadius: "18px",
          padding: "32px",
          boxShadow: "0 20px 40px rgba(15, 23, 42, 0.35)",
        }}>
          <p style={{ margin: "0 0 12px", letterSpacing: "0.12em", textTransform: "uppercase", color: "#cbd5e1" }}>
            Nexus access portal
          </p>
          <h1 style={{ margin: "0 0 14px", fontSize: "2.2rem" }}>Sign in to continue</h1>
          <p style={{ color: "#cbd5e1", marginTop: 0 }}>
            Secure operational access for finance, approvals, procurement, and admin workflows.
          </p>

          <div style={{ display: "grid", gap: "16px", marginTop: "28px" }}>
            {ROLE_DEFINITIONS.map((role) => (
              <div key={role.key} style={{
                border: "1px solid rgba(148, 163, 184, 0.2)",
                borderRadius: "12px",
                background: "rgba(30, 41, 59, 0.8)",
                padding: "12px 14px",
              }}>
                <strong>{role.label}</strong>
                <div style={{ color: "#cbd5e1", fontSize: "0.9rem", marginTop: "4px" }}>
                  {role.description}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section style={{
          background: "rgba(255,255,255,0.96)",
          borderRadius: "18px",
          padding: "32px",
          color: "#111827",
          boxShadow: "0 20px 40px rgba(15, 23, 42, 0.35)",
        }}>
          <h2 style={{ marginTop: 0 }}>Welcome back</h2>
          <form onSubmit={handleSubmit} style={{ display: "grid", gap: "16px" }}>
            <label style={{ display: "grid", gap: "8px" }}>
              <span>Email</span>
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                required
                style={{ padding: "12px 14px", borderRadius: "10px", border: "1px solid #cbd5e1" }}
              />
            </label>

            <label style={{ display: "grid", gap: "8px" }}>
              <span>Password</span>
              <input
                name="password"
                type="password"
                value={form.password}
                onChange={handleChange}
                required
                style={{ padding: "12px 14px", borderRadius: "10px", border: "1px solid #cbd5e1" }}
              />
            </label>

            {error && (
              <div style={{ background: "#fef2f2", color: "#b91c1c", borderRadius: "10px", padding: "10px 12px" }}>
                {error}
              </div>
            )}

            <button type="submit" disabled={submitting} style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "10px",
              padding: "12px 16px",
              fontSize: "1rem",
              cursor: "pointer",
            }}>
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
