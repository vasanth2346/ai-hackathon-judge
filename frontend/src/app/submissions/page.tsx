"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, Plus, Search } from "lucide-react";
import { api, Submission } from "@/lib/api";
import { JudgeActions } from "@/components/judge-actions";

export default function SubmissionsPage(){
  const [rows,setRows]=useState<Submission[]>([]); const [error,setError]=useState(""); const [query,setQuery]=useState("");
  async function refresh(){const next=await api<Submission[]>("/api/submissions");setRows(next);setError("");}
  useEffect(()=>{refresh().catch(e=>setError(e.message));},[]);
  const visible=rows.filter(r=>`${r.application_number||""} ${r.project_name} ${r.participant_names.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  return <><div className="header-row"><div><div className="eyebrow">WORKSPACE / ENTRIES</div><h1 className="page-title">Projects</h1><p className="page-subtitle">Application ID, details, judging status, and latest evidence.</p></div><Link className="primary-btn" href="/submissions/new"><Plus size={15}/> Add a project</Link></div>
    {error&&<div className="error-banner">Could not load submissions: {error}</div>}
    <section className="panel"><div className="panel-heading"><div><div className="panel-title">All projects</div><div className="panel-kicker" style={{marginTop:4}}>{rows.length} {rows.length===1?"entry":"entries"}</div></div><div className="field" style={{margin:0,width:220,position:"relative"}}><Search size={14} style={{position:"absolute",left:10,top:10,color:"#9aa49e"}}/><input aria-label="Search projects" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search ID, name, participant…" style={{paddingLeft:31}}/></div></div>
    {visible.length?<div className="submission-list">{visible.map(row=><div className="submission-card" key={row.id}><Link className="submission-info" href={`/submissions/${row.id}`}><span className="project-avatar" style={{width:37,height:37}}>{row.project_name.slice(0,1).toUpperCase()}</span><div style={{minWidth:0}}><div className="submission-title">{row.project_name}</div><div className="submission-meta">ID {row.application_number||"legacy"} · {row.participant_names[0]} · <span style={{color:"#43846c"}}>{row.deployed_url}</span></div></div></Link><Link className="submission-right" href={`/submissions/${row.id}`}>{row.latest_run?.total_score!=null?<span className="score-big">{row.latest_run.total_score.toFixed(1)}<small style={{fontSize:8,color:"#91a099"}}> /100</small></span>:<span className={`status-pill ${row.latest_run?.status||"queued"}`}><span className="status-dot"/>{row.latest_run?.status||"Not judged"}</span>}<ArrowRight size={15} color="#9aa59f"/></Link><JudgeActions submissionId={row.id} onComplete={refresh}/></div>)}</div>:<div className="empty-state"><div><b>{query?"No matching projects":"No projects yet"}</b>{query?"Try another ID or name.":"Add your first project."}{!query&&<div style={{marginTop:12}}><Link href="/submissions/new" className="text-link">Add a project <ArrowRight size={13}/></Link></div>}</div></div>}</section>
  </>;
}
