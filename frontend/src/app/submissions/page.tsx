"use client";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowRight, Check, Search } from "lucide-react";
import { api, Submission } from "@/lib/api";
import { JudgeActions } from "@/components/judge-actions";

type BatchResult = { queued: number; already_active: number; not_found: number };

export default function SubmissionsPage(){
  const [rows,setRows]=useState<Submission[]>([]);
  const [error,setError]=useState("");
  const [query,setQuery]=useState("");
  const [selected,setSelected]=useState<Set<string>>(new Set());
  const [batchBusy,setBatchBusy]=useState(false);
  const [message,setMessage]=useState("");
  const refresh=useCallback(async()=>{const next=await api<Submission[]>("/api/submissions");setRows(next);setError("");},[]);
  useEffect(()=>{
    refresh().catch(e=>setError(e.message));
    const timer=window.setInterval(()=>refresh().catch(e=>setError(e.message)),5000);
    return()=>window.clearInterval(timer);
  },[refresh]);
  useEffect(()=>{if(!message)return;const timer=window.setTimeout(()=>setMessage(""),5000);return()=>window.clearTimeout(timer);},[message]);
  const visible=rows.filter(r=>`${r.application_number||""} ${r.project_name} ${r.participant_names.join(" ")}`.toLowerCase().includes(query.toLowerCase()));
  const allVisibleSelected=visible.length>0&&visible.every(row=>selected.has(row.id));
  function toggleOne(id:string){setSelected(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next;});}
  function toggleVisible(){setSelected(current=>{const next=new Set(current);if(allVisibleSelected)visible.forEach(row=>next.delete(row.id));else visible.forEach(row=>next.add(row.id));return next;});}
  async function evaluate(ids?:string[]){
    setBatchBusy(true);setError("");setMessage("");
    try{
      const result=await api<BatchResult>("/api/submissions/evaluate-batch",{method:"POST",body:JSON.stringify(ids?{submission_ids:ids}:{})});
      setMessage(`${result.queued} project${result.queued===1?"":"s"} queued${result.already_active?` · ${result.already_active} already evaluating`:""}.`);
      if(ids)setSelected(new Set());
      await refresh();
    }catch(e){setError(e instanceof Error?e.message:"Could not queue project evaluations.");}
    finally{setBatchBusy(false);}
  }
  return <>
    <div className="header-row"><div><div className="eyebrow">WORKSPACE / ENTRIES</div><h1 className="page-title">Projects</h1><p className="page-subtitle">Select projects to evaluate together. Scores appear as each evaluation finishes.</p></div></div>
    {error&&<div className="error-banner">{error}</div>}
    {message&&<div className="success-banner" role="status">{message}</div>}
    <section className="panel"><div className="panel-heading"><div><div className="panel-title">All projects</div><div className="panel-kicker" style={{marginTop:4}}>{rows.length} {rows.length===1?"entry":"entries"}</div></div><div style={{display:"flex",alignItems:"center",justifyContent:"flex-end",gap:14,flexWrap:"wrap"}}><label style={{display:"inline-flex",alignItems:"center",gap:6,fontSize:10,cursor:"pointer",whiteSpace:"nowrap"}}><input type="checkbox" aria-label="Select all visible projects" checked={allVisibleSelected} onChange={toggleVisible}/> Select all</label><div className="field" style={{margin:0,width:220,position:"relative"}}><Search size={14} style={{position:"absolute",left:10,top:10,color:"#9aa49e"}}/><input aria-label="Search projects" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search ID, name, participant…" style={{paddingLeft:31}}/></div></div></div>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",gap:12,flexWrap:"wrap",margin:"12px 0 14px"}}><span className="panel-kicker">{selected.size} selected · evaluations run as workers become available</span><div style={{display:"flex",gap:8,flexWrap:"wrap"}}><button className="secondary-btn" type="button" disabled={!selected.size||batchBusy} onClick={()=>evaluate([...selected])}>{batchBusy?"Queuing…":"Evaluate selected"}</button><button className="primary-btn" type="button" disabled={!rows.length||batchBusy} onClick={()=>evaluate()}>{batchBusy?<><span>Queuing projects…</span></>:<><Check size={14}/> Evaluate all projects</>}</button></div></div>
      {visible.length?<div className="submission-list">{visible.map(row=><div className="submission-card" key={row.id}><input type="checkbox" aria-label={`Select ${row.project_name}`} checked={selected.has(row.id)} onChange={()=>toggleOne(row.id)} style={{flexShrink:0}}/><Link className="submission-info" href={`/submissions/${row.id}`}><span className="project-avatar" style={{width:37,height:37}}>{row.project_name.slice(0,1).toUpperCase()}</span><div style={{minWidth:0}}><div className="submission-title">{row.project_name}</div><div className="submission-meta">ID {row.application_number||"legacy"} · {row.participant_names[0]} · <span style={{color:"#43846c"}}>{row.deployed_url}</span></div></div></Link><Link className="submission-right" href={`/submissions/${row.id}`}>{row.latest_run?.total_score!=null?<span className="score-big">{row.latest_run.total_score.toFixed(1)}<small style={{fontSize:8,color:"#91a099"}}> /100</small></span>:<span className={`status-pill ${row.latest_run?.status||"queued"}`}><span className="status-dot"/>{row.latest_run?.status||"Not judged"}</span>}<ArrowRight size={15} color="#9aa59f"/></Link><JudgeActions submissionId={row.id} onComplete={refresh}/></div>)}</div>:<div className="empty-state"><div><b>{query?"No matching projects":"No projects yet"}</b>{query?"Try another ID or name.":"Projects submitted by participants will appear here."}</div></div>}
    </section>
  </>;
}
