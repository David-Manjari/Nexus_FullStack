import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../../auth/AuthContext";
import { ROLE_DEFINITIONS } from "../../roles";

export default function LoginPage() {
  const navigate = useNavigate();
  const {
    login,
    setupTotp,
    verifyMfaMethod,
    completeLogin,
    user,
  } = useAuth();
  const [form, setForm] = useState({
    email: "",
    password: "",
  });
  const [showPassword, setShowPassword] = useState(false);
  const [step, setStep] = useState("credentials");
  const [setup, setSetup] = useState(null);
  const [mfaOptions, setMfaOptions] = useState(null);
  const [mfaMethod, setMfaMethod] = useState("");
  const [qrExpiresAt, setQrExpiresAt] = useState(null);
  const [qrSecondsRemaining, setQrSecondsRemaining] = useState(0);
  const [code, setCode] = useState("");
  const [verifiedUser, setVerifiedUser] = useState(null);
  const [recoveryCodes, setRecoveryCodes] = useState([]);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (qrExpiresAt === null) return undefined;

    const updateCountdown = () => {
      setQrSecondsRemaining(
        Math.max(0, Math.ceil((qrExpiresAt - Date.now()) / 1000))
      );
    };

    updateCountdown();
    const intervalId = window.setInterval(updateCountdown, 1000);
    return () => window.clearInterval(intervalId);
  }, [qrExpiresAt]);

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
      const response = await login(form);
      setMfaOptions(response);
      setSetup(null);
      setMfaMethod("qr");
      setQrExpiresAt(Date.now() + 5 * 60 * 1000);
      setCode("");
      setStep("mfa");
    } catch (submitError) {
      setError(submitError.message || "Unable to log in.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleChooseTotp = async () => {
    setError("");
    setSubmitting(true);
    try {
      if (!mfaOptions.totp_available) {
        const response = await setupTotp();
        setSetup(response.setup);
      }
      setMfaMethod("totp");
    } catch (submitError) {
      setError(submitError.message || "Could not set up an authenticator.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleMfaSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await verifyMfaMethod(code, mfaMethod);
      if (response.recovery_codes) {
        setVerifiedUser(response.user);
        setRecoveryCodes(response.recovery_codes);
        setStep("recovery");
      } else {
        completeLogin(response.user);
        navigate("/dashboard", { replace: true });
      }
    } catch (submitError) {
      setError(submitError.message || "Could not verify your code.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleRecoverySaved = () => {
    completeLogin(verifiedUser);
    navigate("/dashboard", { replace: true });
  };

  const handleStartOver = () => {
    setSetup(null);
    setMfaOptions(null);
    setMfaMethod("");
    setQrExpiresAt(null);
    setQrSecondsRemaining(0);
    setCode("");
    setError("");
    setStep("credentials");
  };

  return (
    <div className="login-page" style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--color-page)",
      color: "var(--color-ink)",
      fontFamily: "inherit",
    }}>
      <div className="login-panels">
        <section style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "12px",
          padding: "32px",
          boxShadow: "0 8px 20px rgba(32, 52, 45, 0.05)",
        }}>
          <p style={{ margin: "0 0 12px", letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--color-primary)" }}>
            Nexus access portal
          </p>
          <h1 style={{ margin: "0 0 14px", fontSize: "2.2rem" }}>Sign in to continue</h1>
          <p style={{ color: "var(--color-muted)", marginTop: 0 }}>
            Secure operational access for finance, approvals, procurement, and admin workflows.
          </p>

          <div style={{ display: "grid", gap: "16px", marginTop: "28px" }}>
            {ROLE_DEFINITIONS.map((role) => (
              <div key={role.key} style={{
                border: "1px solid var(--color-border)",
                borderRadius: "12px",
                background: "var(--color-surface-muted)",
                padding: "12px 14px",
              }}>
                <strong>{role.label}</strong>
                <div style={{ color: "var(--color-muted)", fontSize: "0.9rem", marginTop: "4px" }}>
                  {role.description}
                </div>
              </div>
            ))}
          </div>
        </section>

        <section style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "12px",
          padding: "32px",
          color: "var(--color-ink)",
          boxShadow: "0 8px 20px rgba(32, 52, 45, 0.05)",
        }}>
          <h2 style={{ marginTop: 0 }}>Welcome back</h2>
          {step === "credentials" && <form onSubmit={handleSubmit} style={{ display: "grid", gap: "16px" }}>
            <label style={{ display: "grid", gap: "8px" }}>
              <span>Email</span>
              <input
                name="email"
                type="email"
                value={form.email}
                onChange={handleChange}
                required
                style={{ padding: "12px 14px", borderRadius: "8px", border: "1px solid var(--color-border)" }}
              />
            </label>

            <label style={{ display: "grid", gap: "8px" }}>
              <span>Password</span>
              <div style={{ display: "flex", gap: "8px" }}>
                <input
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={form.password}
                  onChange={handleChange}
                  required
                  style={{ flex: 1, minWidth: 0, padding: "12px 14px", borderRadius: "8px", border: "1px solid var(--color-border)" }}
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
            </label>

            {error && (
              <div style={{ background: "#fef2f2", color: "#b91c1c", borderRadius: "10px", padding: "10px 12px" }}>
                {error}
              </div>
            )}

            <button type="submit" disabled={submitting} style={{
              background: "var(--color-primary)",
              color: "#fff",
              border: "none",
              borderRadius: "10px",
              padding: "12px 16px",
              fontSize: "1rem",
              cursor: "pointer",
            }}>
              {submitting ? "Signing in..." : "Sign in"}
            </button>
          </form>}
          {step === "mfa" && (
            <div>
              {!mfaMethod && (
                <div style={{ display: "grid", gap: "12px" }}>
                  <p>
                    Select a way to continue signing in.
                  </p>
                  <button type="button" onClick={() => setMfaMethod("qr")}>
                    Use QR sign-in code
                  </button>
                  <button type="button" disabled={submitting} onClick={handleChooseTotp}>
                    {mfaOptions?.totp_available
                      ? "Use authenticator app"
                      : "Set up authenticator app backup"}
                  </button>
                  {error && <div role="alert" style={{ background: "#fef2f2", color: "#b91c1c", borderRadius: "10px", padding: "10px 12px" }}>{error}</div>}
                </div>
              )}
              {mfaMethod === "qr" && (
                <div style={{ marginBottom: "18px" }}>
                  <p>Scan the QR code for your login code.</p>
                  <p role="timer" aria-live="off">
                    {qrSecondsRemaining > 0
                      ? `Code expires in ${String(Math.floor(qrSecondsRemaining / 60)).padStart(2, "0")}:${String(qrSecondsRemaining % 60).padStart(2, "0")}`
                      : "Code expired. Start over to get a new QR code."}
                  </p>
                  <div style={{ display: "flex", justifyContent: "center", padding: "16px" }}>
                    <QRCodeSVG
                      value={mfaOptions.qr_code}
                      size={120}
                      level="M"
                      title="One-time sign-in code"
                    />
                  </div>
                  <p>This sign-in code expires in five minutes and can only be used once. Anyone who scans it can use it for this sign-in; it does not verify the scanner's identity.</p>
                </div>
              )}
              {setup && (
                <div style={{ marginBottom: "18px" }}>
                  <p>Scan this QR code with your authenticator app, then enter the six-digit code it generates.</p>
                  <div style={{ display: "flex", justifyContent: "center", padding: "16px" }}>
                    <QRCodeSVG
                      value={setup.otpauth_url}
                      size={120}
                      level="M"
                      title="Authenticator app setup QR code"
                    />
                  </div>
                  <p>If you cannot scan the code, add the account manually:</p>
                  <p><strong>Account:</strong> {form.email}</p>
                  <p><strong>Issuer:</strong> {setup.issuer}</p>
                  <p><strong>Setup key:</strong></p>
                  <code style={{ display: "block", overflowWrap: "anywhere", padding: "12px", background: "var(--color-surface-muted)", borderRadius: "8px" }}>
                    {setup.secret}
                  </code>
                  <p>Enter the six-digit code from the app to finish setup. Save the recovery codes shown after verification.</p>
                </div>
              )}
              {mfaMethod === "totp" && !setup && (
                <p>Enter the code from your authenticator app.</p>
              )}
              {mfaMethod === "recovery" && (
                <p>Enter one of your unused recovery codes.</p>
              )}
              {mfaMethod && (
              <form onSubmit={handleMfaSubmit} style={{ display: "grid", gap: "16px" }}>
                <label style={{ display: "grid", gap: "8px" }}>
                  <span>
                    {mfaMethod === "recovery"
                      ? "Recovery code"
                      : mfaMethod === "qr"
                        ? "QR sign-in code"
                        : "Authenticator code"}
                  </span>
                  <input
                    name="code"
                    type="text"
                    autoComplete="one-time-code"
                    value={code}
                    onChange={(event) => setCode(event.target.value)}
                    required
                    maxLength={64}
                    autoFocus
                    style={{ padding: "12px 14px", borderRadius: "8px", border: "1px solid var(--color-border)" }}
                  />
                </label>
                {error && <div role="alert" style={{ background: "#fef2f2", color: "#b91c1c", borderRadius: "10px", padding: "10px 12px" }}>{error}</div>}
                <button type="submit" disabled={submitting} style={{
                  background: "var(--color-primary)",
                  color: "#fff",
                  border: "none",
                  borderRadius: "10px",
                  padding: "12px 16px",
                  fontSize: "1rem",
                  cursor: "pointer",
                }}>
                  {submitting ? "Verifying..." : "Verify and continue"}
                </button>
              </form>
              )}
              {mfaMethod && (
                <div style={{ display: "flex", gap: "10px", marginTop: "12px" }}>
                  {mfaMethod === "qr" && (
                    <button type="button" disabled={submitting} onClick={handleChooseTotp}>
                      {mfaOptions?.totp_available
                        ? "Use authenticator app instead"
                        : "Set up authenticator app backup"}
                    </button>
                  )}
                  {mfaMethod !== "recovery" && (
                    <button type="button" onClick={() => { setMfaMethod("recovery"); setCode(""); }}>
                      Use a recovery code
                    </button>
                  )}
                  {mfaMethod !== "qr" && (
                    <button type="button" onClick={() => { setMfaMethod("qr"); setSetup(null); setCode(""); setError(""); }}>
                      Use QR sign-in code
                    </button>
                  )}
                  <button type="button" onClick={handleStartOver}>
                    Start over
                  </button>
                </div>
              )}
            </div>
          )}
          {step === "recovery" && (
            <div>
              <p><strong>Save these recovery codes somewhere safe.</strong> Each code works once if you lose access to your sign-in methods. They will not be shown again.</p>
              <ul aria-label="Recovery codes" style={{ columns: 2, fontFamily: "monospace" }}>
                {recoveryCodes.map((recoveryCode) => <li key={recoveryCode}>{recoveryCode}</li>)}
              </ul>
              <button type="button" onClick={handleRecoverySaved} style={{
                background: "var(--color-primary)",
                color: "#fff",
                border: "none",
                borderRadius: "10px",
                padding: "12px 16px",
                fontSize: "1rem",
                cursor: "pointer",
              }}>
                I saved my recovery codes
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
