"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, ClipboardCheck, Gauge, Globe2, Medal, Plus, Radar, ShieldAlert, Sparkles, UploadCloud } from "lucide-react";
import { api, Leader, Submission, upload } from "@/lib/api";

type RegistrationImport = {uploaded:boolean;participant_count:number;created_count:number;updated_count:number;skipped_count:number;email_missing_count:number;status_lines:string[]};

export default function Dashboard() {
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [leaders, setLeaders] = useState<Leader[]>([]);
  const [error, setError] = useState("");
  const [registrationFile, setRegistrationFile] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  async function refresh(){const [s,l]=await Promise.all([api<Submission[]>("/api/submissions"),api<Leader[]>("/api/leaderboard")]);setSubmissions(s);setLeaders(l);}
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    const timer = window.setInterval(() => refresh().catch((e) => setError(e.message)), 15000);
    return () => window.clearInterval(timer);
  }, []);
  async function importRegistration(event:React.FormEvent<HTMLFormElement>){event.preventDefault();const form=event.currentTarget;setUploadError("");setUploadMessage("");if(!registrationFile){setUploadError("Choose a registration file first.");return;}setUploading(true);const data=new FormData();data.set("pdf",registrationFile);try{const result=await upload<RegistrationImport>("/api/host/registrations",data);setUploadMessage(result.status_lines.join("\n"));setRegistrationFile(null);form.reset();await refresh();}catch(e){setUploadError(e instanceof Error?e.message:"Could not upload registration file.");}finally{setUploading(false);}}
  const completed = submissions.filter(s => s.latest_run?.status === "completed");
  const active = submissions.filter(s => ["queued","running"].includes(s.latest_run?.status || ""));
  const avg = completed.length ? (completed.reduce((sum,s) => sum + (s.latest_run?.total_score || 0),0)/completed.length).toFixed(1) : "—";
  return <>
    <div className="header-row"><div><div className="eyebrow">JUDGING CONSOLE</div><h1 className="page-title">Good work starts with proof.</h1><p className="page-subtitle">A clear view of every project, every test, and every score.</p></div><Link href="#participant-registrations" className="primary-btn"><Plus size={15}/> Upload participant registrations</Link></div>
    {error && <div className="error-banner">Can’t connect to the judging API. Start the local services to load live submissions. <span style={{opacity:.8}}>{error}</span></div>}
    <div className="stats-grid">
      <Stat label="SUBMISSIONS" value={String(submissions.length).padStart(2,"0")} note="All entries" icon={<ClipboardCheck size={16}/>} />
      <Stat label="JUDGED" value={String(completed.length).padStart(2,"0")} note="Completed reports" icon={<CheckCircle2 size={16}/>} />
      <Stat label="IN PROGRESS" value={String(active.length).padStart(2,"0")} note="Live judge jobs" icon={<Radar size={16}/>} />
      <Stat label="AVERAGE SCORE" value={avg} note="Out of 100 points" icon={<Gauge size={16}/>} />
    </div>
    <div className="dashboard-grid">
      <section className="panel"><div className="panel-heading"><div><div className="panel-title">Recent projects</div><div className="panel-kicker" style={{marginTop:4}}>Latest entries</div></div><Link className="text-link" href="/submissions">All projects <ArrowRight size={13}/></Link></div>
      {submissions.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>APPLICATION ID</th><th>PROJECT</th><th>SUBMITTED</th><th>STATUS</th><th>SCORE</th></tr></thead><tbody>{submissions.slice(0,5).map(item=><tr key={item.id}><td>{item.application_number||"—"}</td><td><Link className="project-cell" href={`/submissions/${item.id}`}><span className="project-avatar">{item.project_name.slice(0,1).toUpperCase()}</span>{item.project_name}</Link></td><td>{new Date(item.created_at).toLocaleDateString(undefined,{month:"short",day:"numeric"})}</td><td><Status status={item.latest_run?.status || "submitted"}/></td><td>{item.latest_run?.total_score != null ? <span className="score-pill">{item.latest_run.total_score.toFixed(1)}</span> : <span style={{color:"#b2bbb6"}}>—</span>}</td></tr>)}</tbody></table></div> : <Empty icon={<ClipboardCheck size={17}/>} title="No projects yet" body="Add the first project." action={<Link href="/submissions/new" className="text-link">Add a project <ArrowRight size={13}/></Link>}/>}</section>
      <div className="panel steps-card"><div className="panel-title">How the judge works</div><p>The deployed product is the primary evidence. The report keeps what was observed separate from what the judge concludes.</p><div className="steps-list"><Step num="01" text="Read the participant registration and project details"/><Step num="02" text="Open the participant’s live app"/><Step num="03" text="Capture screenshots, errors and signals"/><Step num="04" text="Explain score gaps with evidence"/></div></div>
    </div>
    <section id="participant-registrations" className="panel" style={{marginTop:13,scrollMarginTop:16}}><div className="panel-heading"><div><div className="panel-title">Participant registrations</div><div className="panel-kicker" style={{marginTop:4}}>Import a roster for this host account</div></div><UploadCloud size={16} color="#438b6d"/></div>
      <form onSubmit={importRegistration} style={{display:"flex",gap:9,alignItems:"end",flexWrap:"wrap",margin:"12px 0"}}><div className="field" style={{flex:"1 1 300px"}}><label htmlFor="registration-file">Registration file</label><input id="registration-file" type="file" accept="application/pdf,.pdf,text/csv,.csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,.xlsx,.xlsm" onChange={e=>setRegistrationFile(e.target.files?.[0]||null)} required style={{padding:8}}/><span className="field-note">Supported formats: searchable PDF, CSV, and Excel (.xlsx or .xlsm). Include participant name and email; phone is stored when provided. Each roster and its submissions stay with the host who uploaded it.</span></div><button className="primary-btn" disabled={uploading}>{uploading?"Uploading file…":"Upload roster"}<UploadCloud size={14}/></button></form>
      {uploadMessage&&<div className="status-pill complete" style={{marginBottom:10,whiteSpace:"pre-line",lineHeight:1.7}}>{uploadMessage}</div>}{uploadError&&<div className="error-banner">{uploadError}</div>}
    </section>
    <div className="dashboard-grid" style={{marginTop:13}}>
      <section className="panel"><div className="panel-heading"><div><div className="panel-title">Leaderboard</div><div className="panel-kicker" style={{marginTop:4}}>Latest completed evaluations</div></div><Link className="text-link" href="/leaderboard">View all <ArrowRight size={13}/></Link></div>
        {leaders.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>RANK</th><th>ID</th><th>PROJECT</th><th>SCORE</th></tr></thead><tbody>{leaders.slice(0,4).map(row=><tr key={row.run_id}><td className={`leader-rank ${row.rank===1?"rank-first":""}`}>{String(row.rank).padStart(2,"0")}</td><td>{row.application_number||"—"}</td><td><Link className="project-cell" href={`/reports/${row.run_id}`}><span className="project-avatar">{row.project_name.slice(0,1).toUpperCase()}</span>{row.project_name}</Link></td><td><span className="score-pill">{row.total_score.toFixed(1)}</span></td></tr>)}</tbody></table></div> : <Empty icon={<Medal size={17}/>} title="No scores on the board yet" body="Completed reports will appear here."/>}</section>
      <section className="panel"><div className="panel-heading"><div className="panel-title">Evaluation principles</div><span className="panel-kicker">EVIDENCE BASED</span></div><div className="bullet-list"><div className="bullet-row"><Globe2 size={14}/>The deployed project is the primary evidence.</div><div className="bullet-row"><ShieldAlert size={14}/>Conflicting evidence or low confidence is flagged for review.</div><div className="bullet-row"><Sparkles size={14}/>Browser tests link to recorded observations.</div></div></section>
    </div>
    <section className="panel rubric-panel"><div className="panel-heading"><div><div className="panel-title">The published rubric</div><div className="panel-kicker" style={{marginTop:4}}>100 points across six criteria</div></div><span className="status-pill complete"><span className="status-dot"/> 100% TOTAL</span></div><div className="rubric-grid">{[["30%","Working Functionality"],["20%","Problem Fit"],["10%","Technical Complexity"],["10%","UI/UX & Usability"],["20%","Innovation & Originality"],["10%","Real-World Problem Potential"]].map(([score,name])=><div className="rubric-item" key={name}><b>{score}</b><span>{name}</span></div>)}</div></section>
  </>;
}
function Stat({label,value,note,icon}:{label:string;value:string;note:string;icon:React.ReactNode}){return <div className="stat-card"><div className="stat-label">{label}</div><span className="stat-icon">{icon}</span><div className="stat-value">{value}</div><div className="stat-note">{note}</div></div>}
function Empty({icon,title,body,action}:{icon:React.ReactNode;title:string;body:string;action?:React.ReactNode}){return <div className="empty-state"><div><div className="empty-icon">{icon}</div><b>{title}</b>{body}{action&&<div style={{marginTop:12}}>{action}</div>}</div></div>}
function Status({status}:{status:string}){const key=["completed","queued","running","failed"].includes(status)?status:"queued";return <span className={`status-pill ${key}`}><span className="status-dot"/>{status==="completed"?"Judged":status==="queued"?"Submitted":status==="running"?"In progress":status==="failed"?"Failed":"Submitted"}</span>}
function Step({num,text}:{num:string;text:string}){return <div className="step-item"><span className="step-num">{num}</span>{text}</div>}
