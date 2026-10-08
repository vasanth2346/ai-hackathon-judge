"use client";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { API_URL, api } from "@/lib/api";

type Role = "host" | "participant";
type Props = { role: Role };
const errors: Record<string, string> = {
  host_google_disabled: "Host accounts use Host Login with the credentials provisioned by the event administrator.",
  google_not_configured: "Google sign-in is not set up yet. Add the OAuth client ID and secret to .env.",
  account_not_found: "No account found for this Google account. Choose sign up first.",
  account_role_mismatch: "This Google account is registered for the other account type.",
  participant_id_mismatch: "This Google account is already linked to a different participant ID.",
  google_email_unverified: "Verify your email with Google, then try again.",
  oauth_state_invalid: "Sign-in expired. Please try again.",
  google_signin_failed: "Google sign-in could not be completed. Please try again.",
};

export function GoogleAuthForm({ role }: Props) {
  const router = useRouter();
  const [intent, setIntent] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [configured, setConfigured] = useState(false);
  const [missingOAuthSettings, setMissingOAuthSettings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const hostRole = role === "host";

  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const mode = query.get("mode");
    if (mode === "signup" && !hostRole) setIntent("signup");
    const errorCode = query.get("error");
    if (errorCode) window.history.replaceState({}, document.title, window.location.pathname + (mode === "signup" ? "?mode=signup" : ""));
    if (hostRole) { setConfigured(false); setLoading(false); return; }
    api<{ configured: boolean; checks?: Record<string, boolean> }>("/api/auth/google/status").then(result => {
      setConfigured(result.configured);
      const envNames: Record<string, string> = {
        google_client_id: "GOOGLE_CLIENT_ID",
        google_client_secret: "GOOGLE_CLIENT_SECRET",
        auth_secret_key: "AUTH_SECRET_KEY",
        google_redirect_uri: "GOOGLE_REDIRECT_URI",
      };
      setMissingOAuthSettings(Object.entries(result.checks || {}).filter(([, present]) => !present).map(([name]) => envNames[name] || name));
      if (result.configured && errorCode) setError(errors[errorCode] || "Sign-in failed. Please try again.");
    }).catch(() => setConfigured(false)).finally(() => setLoading(false));
  }, [hostRole]);

  function beginGoogle() {
    setError("");
    const query = new URLSearchParams({ role, intent });
    window.location.assign(`${API_URL}/api/auth/google/start?${query.toString()}`);
  }

  async function submitEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api(`/api/auth/email/${intent}`, { method: "POST", body: JSON.stringify({ role, email, password }) });
      router.replace(role === "host" ? "/host-dashboard" : "/participant");
    } catch (e) { setError(e instanceof Error ? e.message : "Could not sign in"); setBusy(false); }
  }

  return <main className="auth-page"><section className="auth-card"><Link className="brand auth-brand" href="/"><span className="brand-icon">P</span><span>proof<span className="brand-dot">.</span><small>HACKATHON JUDGE</small></span></Link><h1>{hostRole ? "Host login" : "Participant account"}</h1><p>{hostRole ? "Sign in to manage projects and evaluations." : "Access your registration and submit your project."}</p>
    {!hostRole && <div className="auth-tabs" role="tablist"><button type="button" role="tab" aria-selected={intent === "signin"} className={intent === "signin" ? "selected" : ""} onClick={() => { setIntent("signin"); setError(""); }}>Sign in</button><button type="button" role="tab" aria-selected={intent === "signup"} className={intent === "signup" ? "selected" : ""} onClick={() => { setIntent("signup"); setError(""); }}>Sign up</button></div>}
    {!hostRole && intent === "signup" && <div className="auth-setup-note">Use the email listed in a host’s uploaded registration document. Matching that roster is required to create a participant account.</div>}
    <form onSubmit={submitEmail}>
      <div className="field"><label htmlFor="account-email">Email</label><input id="account-email" type="email" autoComplete="email" value={email} onChange={e=>setEmail(e.target.value)} required /></div>
      <div className="field"><label htmlFor="account-password">Password</label><input id="account-password" type="password" autoComplete={intent === "signup" ? "new-password" : "current-password"} minLength={intent === "signup" ? 8 : undefined} value={password} onChange={e=>setPassword(e.target.value)} placeholder={intent === "signup" ? "At least 8 characters" : "Your password"} required /></div>
      {error && <div className="error-banner">{error}</div>}
      <button className="primary-btn auth-submit" type="submit" disabled={busy}>{busy ? "Please wait…" : hostRole ? "Host Login" : intent === "signin" ? "Sign in with email" : "Create account with email"}</button>
    </form>
    {!hostRole && <><div className="auth-or"><span>OR</span></div>
    {!loading && !configured && <div className="auth-setup-note">Google sign-in is not configured. You can still use email and password.{missingOAuthSettings.length > 0 && <> Missing on the backend: {missingOAuthSettings.join(", ")}.</>}</div>}
    <button className="google-button" type="button" onClick={beginGoogle} disabled={loading || !configured}><GoogleMark/>{loading ? "Checking Google sign-in…" : intent === "signin" ? "Continue with Google" : "Sign up with Google"}</button>
    <Link className="auth-switch" href="/host-login">Host Login</Link></>}
  </section></main>;
}

function GoogleMark() { return <svg aria-hidden="true" viewBox="0 0 48 48" width="18" height="18"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5Z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.91c-.58 2.96-2.26 5.48-4.76 7.18l7.73 6C44.39 37.8 46.98 31.73 46.98 24.55Z"/><path fill="#FBBC05" d="M10.54 28.59a14.4 14.4 0 0 1 0-9.18l-7.98-6.19a23.9 23.9 0 0 0 0 21.56l7.98-6.19Z"/><path fill="#34A853" d="M24 48c6.48 0 11.94-2.13 15.92-5.8l-7.73-6c-2.14 1.44-4.88 2.3-8.19 2.3-6.26 0-11.57-4.22-13.46-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48Z"/></svg>; }
