"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowRight, CheckCircle2, ClipboardCheck, Medal, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

type Summary = { project_count: number; judged_count: number };

export default function PublicDashboard() {
  const [summary, setSummary] = useState<Summary>({ project_count: 0, judged_count: 0 });
  const [role, setRole] = useState("");
  useEffect(() => {
    api<Summary>("/api/public/dashboard").then(setSummary).catch(() => undefined);
    api<{role:string}>("/api/auth/me").then(value => setRole(value.role)).catch(() => setRole(""));
  }, []);
  async function signOut() { try { await api(`/api/auth/logout?role=${role}`, { method: "POST" }); } finally { setRole(""); } }
  return <main className="public-dashboard">
    <header className="public-topbar"><Link className="brand" href="/"><span className="brand-icon">P</span><span>proof<span className="brand-dot">.</span><small>HACKATHON JUDGE</small></span></Link>
      <nav className="public-auth-nav" aria-label="Account access">{role === "host" ? <><Link className="primary-btn" href="/host-dashboard">Host dashboard <ArrowRight size={14}/></Link><button className="secondary-btn" onClick={signOut}>Sign out</button></> : role === "participant" ? <Link className="primary-btn" href="/participant">My project <ArrowRight size={14}/></Link> : <><div className="public-auth-group"><b>Host</b><Link href="/host-login">Sign in</Link><Link href="/host-login?mode=signup">Sign up</Link></div><span className="public-nav-divider"/><div className="public-auth-group"><b>Participant</b><Link href="/participant-login">Sign in</Link><Link href="/participant-login?mode=signup">Sign up</Link></div></>}</nav>
    </header>
    <section className="public-hero"><div className="eyebrow">PROJECT JUDGING DASHBOARD</div><h1>Every score should have proof.</h1><p>Projects are evaluated against the published rubric using observed evidence from the deployed app.</p><div className="public-hero-actions"><Link className="primary-btn" href="/participant-login">Participant access <ArrowRight size={14}/></Link><Link className="secondary-btn" href="/host-login">Host access</Link></div></section>
    <section className="public-stats"><SummaryCard icon={<ClipboardCheck size={17}/>} label="PROJECTS" value={summary.project_count}/><SummaryCard icon={<CheckCircle2 size={17}/>} label="EVALUATED" value={summary.judged_count}/><SummaryCard icon={<ShieldCheck size={17}/>} label="SCORING" value="100 points"/></section>
    <section className="panel public-rubric"><div className="panel-heading"><div><div className="panel-title">Published rubric</div><div className="panel-kicker" style={{marginTop:4}}>Six criteria · 100 points total</div></div><Medal size={17} color="#438b6d"/></div><div className="rubric-grid">{[["30%","Working Functionality"],["20%","Problem Fit"],["10%","Technical Complexity"],["10%","UI/UX & Usability"],["20%","Innovation & Originality"],["10%","Real-World Problem Potential"]].map(([score,name])=><div className="rubric-item" key={name}><b>{score}</b><span>{name}</span></div>)}</div></section>
    <footer className="public-footer">The deployed project is the primary evidence. Reports explain score gaps and flag cases that need human review.</footer>
  </main>;
}

function SummaryCard({icon,label,value}:{icon:React.ReactNode;label:string;value:string|number}){return <div className="public-stat-card"><span>{icon}</span><div><div className="stat-label">{label}</div><strong>{value}</strong></div></div>}
