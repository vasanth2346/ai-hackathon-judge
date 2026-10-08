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
    try { await api("/api/auth/logout", { method: "POST" }); }
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

  if (loading) return <div className="auth-loading">Loading participant account…</div>;
  if (!details) return <main className="participant-page"><section className="panel" style={{maxWidth:560,margin:"50px auto"}}><div className="error-banner">{error || "Could not load participant account."}</div><button className="secondary-btn" onClick={signOut}>Back to sign in</button></section></main>;
  const report = details.report;

  return <main className="participant-page">
    <header className="participant-top"><span className="brand"><span className="brand-icon">P</span><span>proof<span className="brand-dot">.</span><small>PARTICIPANT</small></span></span><button className="secondary-btn" onClick={signOut}>Sign out</button></header>
    <section className="participant-content">
      {!details.linked ? <section className="panel" style={{marginTop:40,maxWidth:620,marginInline:"auto"}}>
        <div className="eyebrow">PARTICIPANT REGISTRATION</div>
        <h1 className="page-title" style={{marginTop:8}}>Registration not found</h1>
        <p className="participant-copy">{details.registration_message || "No host registration matches this account email."}</p>
        <p className="participant-copy" style={{marginTop:10}}>Signed-in email: <b>{details.email}</b></p>
        <button className="secondary-btn" style={{marginTop:16}} onClick={signOut}>Sign out</button>
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
            <div className="field"><label>Description <span className="required">*</span></label><textarea name="solution_description" required minLength={10} maxLength={4000} rows={4}/></div>
            {error && <div className="error-banner">{error}</div>}
            <button className="primary-btn" disabled={saving}>{saving ? "Submitting…" : "Submit project"}</button>
          </div></form>
        </section> : <>
          <h2 className="page-title" style={{marginTop:22}}>{details.project_name}</h2>
          <section className="detail-hero participant-score"><div><h2>Evaluation</h2><p>{details.evaluation_status === "completed" ? "Your project evaluation is ready." : details.evaluation_status === "running" || details.evaluation_status === "queued" ? "Your project is being evaluated." : "Your project has been received."}</p></div><div className="detail-score">{details.total_score != null ? <><strong>{details.total_score.toFixed(1)}</strong><span> / 100</span></> : <span>{details.evaluation_status === "failed" ? "Retry pending" : "Pending"}</span>}</div></section>
          <div className="participant-details"><section className="panel"><h2 className="panel-title">Problem statement</h2><p className="participant-copy">{details.problem_statement}</p><h2 className="panel-title participant-heading">Description</h2><p className="participant-copy">{details.solution_description}</p><a href={details.deployed_url} target="_blank" rel="noreferrer" className="text-link">Open live project ↗</a>{details.github_url && <p><a href={details.github_url} target="_blank" rel="noreferrer" className="text-link">GitHub repository ↗</a></p>}</section>
            {report && <section className="panel"><h2 className="panel-title">Evaluation details</h2><div className="criterion-list">{report.criteria?.map((item:any)=><article key={item.key} className="criterion-card"><div className="criterion-top"><span className="criterion-name">{item.name}</span><span className="criterion-weight">{item.weight}%</span><span className="criterion-points">{item.score} / {item.max_points}</span></div><p className="criterion-rationale">{item.why_points_not_awarded || item.rationale}</p>{item.weaknesses?.length > 0 && <p className="participant-copy">{item.weaknesses.join(" ")}</p>}</article>)}</div></section>}
          </div>
        </>}

        <section className="panel" style={{marginTop:13}}><div className="panel-title">Published rubric</div><div className="rubric-grid" style={{marginTop:12}}>{[["30%","Working Functionality"],["20%","Problem Fit"],["10%","Technical Complexity"],["10%","UI/UX & Usability"],["20%","Innovation & Originality"],["10%","Real-World Potential"]].map(([weight,title])=><div className="rubric-item" key={title}><b>{weight}</b><span>{title}</span></div>)}</div></section>
      </>}
    </section>
  </main>;
}
