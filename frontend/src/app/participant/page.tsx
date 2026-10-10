"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ParticipantDetails, upload } from "@/lib/api";

const domains = [
  "AI for Healthcare",
  "AI for Agriculture",
  "AI for Finance",
  "AI for Cybersecurity",
  "AI for Biotech & Deep Tech",
  "AI for Computer Vision",
  "Open Innovation",
];

export default function ParticipantPage() {
  const router = useRouter();
  const [details, setDetails] = useState<ParticipantDetails | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [selectedDomain, setSelectedDomain] = useState("");

  useEffect(() => {
    api<ParticipantDetails>("/api/participant/me")
      .then(setDetails)
      .catch((e) => {
        if (String(e.message).includes("401")) router.replace("/participant-login");
        else setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [router]);

  async function signOut() {
    try { await api("/api/auth/logout?role=participant", { method: "POST" }); }
    finally { router.replace("/participant-login"); }
  }

  async function submitProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const body = new FormData(event.currentTarget);
    try {
      await upload("/api/participant/submission", body);
      setDetails(await api<ParticipantDetails>("/api/participant/me"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not submit project details.");
    } finally {
      setSaving(false);
    }
  }

  async function verifyRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setVerifying(true);
    setError("");
    const body = new FormData(event.currentTarget);
    try {
      await upload("/api/participant/verify-registration", body);
      setDetails(await api<ParticipantDetails>("/api/participant/me"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not verify this registration.");
    } finally {
      setVerifying(false);
    }
  }

  if (loading) return <div className="auth-loading">Loading participant account…</div>;

  if (!details) return <main className="participant-page">
    <section className="participant-panel participant-unavailable">
      <div className="error-banner">{error || "Could not load participant account."}</div>
      <button className="secondary-btn" onClick={signOut}>Back to sign in</button>
    </section>
  </main>;

  if (!details.linked) return <main className="participant-page">
    <ParticipantHeader onSignOut={signOut} />
    <div className="participant-flow-shell">
      <div className="participant-eyebrow">PARTICIPANT REGISTRATION</div>
      <h1 className="participant-flow-title">Your project, submitted with confidence.</h1>
      <p className="participant-flow-subtitle">Verify the roster email, then add your project details.</p>
      <section className="participant-panel participant-unavailable">
        <h2>Registration not found</h2>
        <p>{details.registration_message || "No host registration matches this account email."}</p>
        <p>Signed-in email: <b>{details.email}</b></p>
        <button className="secondary-btn" onClick={signOut}>Sign out</button>
      </section>
    </div>
  </main>;

  const profileVerified = !details.needs_profile;
  const hasSubmitted = details.has_submission;

  return <main className="participant-page">
    <ParticipantHeader onSignOut={signOut} />
    <div className="participant-flow-shell">
      <div className="participant-eyebrow">PARTICIPANT REGISTRATION</div>
      <h1 className="participant-flow-title">Your project, submitted with confidence.</h1>
      <p className="participant-flow-subtitle">Verify the roster email, then add your project details.</p>

      <div className="participant-flow-grid">
        <section className="participant-panel">
          <div className="participant-step-heading">
            <span className="participant-step-number">1</span>
            <h2>{profileVerified ? "Registration verified" : "Verify your registration"}</h2>
          </div>
          <p className="participant-step-copy">Your verified sign-in email must match the host’s uploaded document.</p>

          {profileVerified ? <div className="participant-form-fields">
            <ReadOnlyField label="Name" value={details.participant_name || "—"} />
            <ReadOnlyField label="Email" value={details.email} verified />
            <ReadOnlyField label="Phone number" value={details.phone || "—"} />
            <ReadOnlyField label="Project domain" value={details.domain || "—"} />
            {details.domain === "Open Innovation" && details.problem_statement && <ReadOnlyField label="Project details" value={details.problem_statement} />}
          </div> : <form className="participant-form-fields" onSubmit={verifyRegistration}>
            <div className="participant-field"><label htmlFor="participant-name">Name <span className="required">*</span></label><input id="participant-name" name="participant_name" defaultValue={details.participant_name} required minLength={2} maxLength={200} /></div>
            <div className="participant-field"><label>Email</label><div className="participant-email-field"><span>{details.email}</span><span className="participant-verified-badge">Verified</span></div></div>
            <div className="participant-field"><label htmlFor="participant-phone">Phone number <span className="required">*</span></label><input id="participant-phone" name="phone" type="tel" defaultValue={details.phone} required minLength={7} maxLength={60} /></div>
            <div className="participant-field"><label htmlFor="participant-domain">Project domain <span className="required">*</span></label><select id="participant-domain" name="domain" value={selectedDomain} onChange={(event) => setSelectedDomain(event.target.value)} required><option value="" disabled>Choose a domain</option>{domains.map((domain) => <option key={domain} value={domain}>{domain}</option>)}</select></div>
            {selectedDomain === "Open Innovation" && <div className="participant-field"><label htmlFor="open-innovation-details">Project details <span className="required">*</span></label><textarea id="open-innovation-details" name="open_innovation_details" required minLength={10} maxLength={4000} rows={4} /><span className="field-note">Describe the project you are doing.</span></div>}
            {error && <div className="error-banner">{error}</div>}
            <button className="primary-btn" disabled={verifying}>{verifying ? "Verifying…" : "Verify registration"}</button>
          </form>}
        </section>

        <section className={`participant-panel${profileVerified ? "" : " participant-panel-locked"}`} aria-disabled={!profileVerified}>
          <div className="participant-step-heading">
            <span className="participant-step-number">2</span>
            <h2>{hasSubmitted ? "Project submitted" : "Project submission"}</h2>
          </div>
          <p className="participant-step-copy">{profileVerified ? "Add your deployed project, repository, and problem statement." : "Available after your sign-in email matches the roster."}</p>

          {hasSubmitted ? <div className="participant-form-fields">
            <ReadOnlyField label="Project name" value={details.project_name} />
            <ReadOnlyField label="Deployed website URL" value={details.deployed_url} />
            <ReadOnlyField label="GitHub repository" value={details.github_url || "—"} />
            <ReadOnlyField label="Problem statement" value={details.problem_statement} />
            <ReadOnlyField label="Domain" value={details.domain || "—"} />
            <div className="participant-status-note"><b>Submission status</b><span>{details.evaluation_status === "completed" ? "Your project has been evaluated." : details.evaluation_status === "running" || details.evaluation_status === "queued" ? "Your project is being evaluated." : "Your project has been received."}</span></div>
          </div> : <form className="participant-form-fields" onSubmit={submitProject}>
            <div className="participant-field"><label htmlFor="project-name">Project name <span className="required">*</span></label><input id="project-name" name="project_name" required minLength={2} maxLength={160} disabled={!profileVerified} /></div>
            <div className="participant-field"><label htmlFor="deployed-url">Deployed website URL <span className="required">*</span></label><input id="deployed-url" name="deployed_url" type="url" placeholder="https://your-project.example" required disabled={!profileVerified} /></div>
            <div className="participant-field"><label htmlFor="github-url">GitHub repository <span className="required">*</span></label><input id="github-url" name="github_url" type="url" placeholder="https://github.com/…" required disabled={!profileVerified} /></div>
            <div className="participant-field"><label htmlFor="problem-statement">Problem statement <span className="required">*</span></label><textarea id="problem-statement" name="problem_statement" placeholder="Describe the problem your project addresses" required minLength={10} maxLength={4000} rows={3} disabled={!profileVerified} /></div>
            <div className="participant-field"><label htmlFor="project-description">Description <span className="field-note">Optional</span></label><textarea id="project-description" name="solution_description" placeholder="Describe your project" maxLength={4000} rows={4} disabled={!profileVerified} /></div>
            <div className="participant-field"><label>Domain</label><div className="participant-email-field">{details.domain || "Selected during registration verification"}</div></div>
            {error && <div className="error-banner">{error}</div>}
            <button className="primary-btn" disabled={!profileVerified || saving}>{saving ? "Submitting…" : "Submit project"}</button>
          </form>}
          {hasSubmitted && <p className="participant-private-note">Your participant view shows submission status only. Scores and evaluation details stay private.</p>}
        </section>
      </div>
    </div>
  </main>;
}

function ParticipantHeader({ onSignOut }: { onSignOut: () => void }) {
  return <header className="participant-flow-header">
    <Link className="brand" href="/"><span className="brand-icon">P</span><span>proof<span className="brand-dot">.</span><small>HACKATHON JUDGE</small></span></Link>
    <button className="secondary-btn" onClick={onSignOut}>Sign out</button>
  </header>;
}

function ReadOnlyField({ label, value, verified = false }: { label: string; value: string; verified?: boolean }) {
  return <div className="participant-field"><label>{label}</label><div className="participant-readonly-field"><span>{value}</span>{verified && <span className="participant-verified-badge">Verified</span>}</div></div>;
}
