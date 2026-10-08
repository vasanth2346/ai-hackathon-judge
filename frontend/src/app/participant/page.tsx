"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ParticipantDetails, upload } from "@/lib/api";

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

  async function submitProject(event: React.FormEvent<HTMLFormElement>) {
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

  async function verifyRegistration(event: React.FormEvent<HTMLFormElement>) {
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
  if (!details) return <main className="participant-page"><section className="panel" style={{maxWidth:560,margin:"50px auto"}}><div className="error-banner">{error || "Could not load participant account."}</div><button className="secondary-btn" onClick={signOut}>Back to sign in</button></section></main>;
  return <main className="participant-page">
    <header className="participant-top"><span className="brand"><span className="brand-icon">P</span><span>proof<span className="brand-dot">.</span><small>PARTICIPANT</small></span></span><button className="secondary-btn" onClick={signOut}>Sign out</button></header>
    <section className="participant-content">
      {!details.linked ? <section className="panel" style={{marginTop:40,maxWidth:620,marginInline:"auto"}}>
        <div className="eyebrow">PARTICIPANT REGISTRATION</div>
        <h1 className="page-title" style={{marginTop:8}}>Registration not found</h1>
        <p className="participant-copy">{details.registration_message || "No host registration matches this account email."}</p>
        <p className="participant-copy" style={{marginTop:10}}>Signed-in email: <b>{details.email}</b></p>
        <button className="secondary-btn" style={{marginTop:16}} onClick={signOut}>Sign out</button>
      </section> : details.needs_profile ? <section className="panel" style={{marginTop:40,maxWidth:620,marginInline:"auto"}}>
        <div className="eyebrow">PARTICIPANT REGISTRATION</div>
        <h1 className="page-title" style={{marginTop:8}}>Verify your registration</h1>
        <p className="participant-copy">Your signed-in email must match the email in the host’s registration document. We use that email to verify your registration.</p>
        <form className="form-layout" onSubmit={verifyRegistration} style={{marginTop:18}}><div className="form-card">
          <div className="field"><label htmlFor="participant-name">Name <span className="required">*</span></label><input id="participant-name" name="participant_name" defaultValue={details.participant_name} required minLength={2} maxLength={200}/></div>
          <p className="field-note" style={{margin:"0 0 6px"}}>Signed in and verified as <b>{details.email}</b>.</p>
          <div className="field"><label htmlFor="participant-phone">Phone number <span className="required">*</span></label><input id="participant-phone" name="phone" type="tel" defaultValue={details.phone} required minLength={7} maxLength={60}/></div>
          <div className="field"><label htmlFor="participant-domain">Project domain <span className="required">*</span></label><select id="participant-domain" name="domain" value={selectedDomain} onChange={event=>setSelectedDomain(event.target.value)} required><option value="" disabled>Select a domain</option>{["AI for Healthcare","AI for Agriculture","AI for Finance","AI for Cybersecurity","AI for Biotech & Deep Tech","AI for Computer Vision","Open Innovation"].map(domain=><option key={domain} value={domain}>{domain}</option>)}</select></div>
          {selectedDomain === "Open Innovation" && <div className="field"><label htmlFor="open-innovation-details">Project details <span className="required">*</span></label><textarea id="open-innovation-details" name="open_innovation_details" required minLength={10} maxLength={4000} rows={4}/><span className="field-note">Describe the project you are doing.</span></div>}
          {error && <div className="error-banner">{error}</div>}
          <button className="primary-btn" disabled={verifying}>{verifying ? "Verifying…" : "Verify registration"}</button>
        </div></form>
      </section> : <>
        <div className="eyebrow">PARTICIPANT DASHBOARD</div>
        <h1 className="page-title" style={{marginTop:8}}>{details.participant_name}</h1>
        <p className="page-subtitle">{details.email}{details.phone ? ` · ${details.phone}` : ""}{details.college_name ? ` · ${details.college_name}` : ""}</p>

        {!details.has_submission ? <section className="panel" style={{marginTop:18}}>
          <div className="panel-title">Submit your project</div>
          <p className="participant-copy">Your registration details are loaded. Complete the project fields to send your submission to the host associated with your registration.</p>
          <form className="form-layout" onSubmit={submitProject} style={{marginTop:14}}><div className="form-card">
            <div className="field"><label>Project name <span className="required">*</span></label><input name="project_name" required minLength={2} maxLength={160}/></div>
            <div className="field"><label>Live project URL <span className="required">*</span></label><input name="deployed_url" type="url" required/></div>
            <div className="field"><label>GitHub repository <span className="required">*</span></label><input name="github_url" type="url" required/></div>
            <div className="field"><label>Problem statement <span className="required">*</span></label><textarea name="problem_statement" required minLength={10} maxLength={4000} rows={3}/></div>
            <div className="field"><label>Description <span className="field-note">Optional</span></label><textarea name="solution_description" maxLength={4000} rows={4}/></div>
            {error && <div className="error-banner">{error}</div>}
            <button className="primary-btn" disabled={saving}>{saving ? "Submitting…" : "Submit project"}</button>
          </div></form>
        </section> : <>
          <h2 className="page-title" style={{marginTop:22}}>{details.project_name}</h2>
          <section className="panel" style={{marginTop:14}}><h2 className="panel-title">Submission status</h2><p className="participant-copy">{details.evaluation_status === "completed" ? "Your project has been evaluated." : details.evaluation_status === "running" || details.evaluation_status === "queued" ? "Your project is being evaluated." : "Your project has been received."}</p></section>
          <div className="participant-details"><section className="panel"><h2 className="panel-title">Project information</h2><div className="section-title" style={{fontSize:10}}>Domain</div><p className="participant-copy">{details.domain || "—"}</p><h2 className="panel-title" style={{marginTop:15}}>Problem statement</h2><p className="participant-copy">{details.problem_statement}</p><a href={details.deployed_url} target="_blank" rel="noreferrer" className="text-link">Open live project ↗</a>{details.github_url && <p><a href={details.github_url} target="_blank" rel="noreferrer" className="text-link">GitHub repository ↗</a></p>}</section>
          </div>
        </>}

      </>}
    </section>
  </main>;
}
