"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Activity, ClipboardList, LayoutDashboard, Medal, Plus, Radar, Scale, ShieldCheck } from "lucide-react";

const nav = [
  { label: "Overview", href: "/host-dashboard", icon: LayoutDashboard },
  { label: "Projects", href: "/submissions", icon: ClipboardList },
  { label: "Leaderboard", href: "/leaderboard", icon: Medal },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [authorized, setAuthorized] = useState(false);
  const [checking, setChecking] = useState(true);
  const isParticipantRoute = pathname === "/participant" || pathname.startsWith("/participant/");
  const isPublic = pathname === "/" || pathname === "/host-login" || pathname === "/participant-login" || isParticipantRoute;
  useEffect(() => {
    if (isPublic) { setChecking(false); return; }
    api<{role:string}>("/api/auth/me").then(session => {
      if (session.role !== "host") throw new Error("Host session required");
      setAuthorized(true);
    }).catch(() => router.replace("/host-login")).finally(() => setChecking(false));
  }, [isPublic, pathname, router]);
  if (isPublic) return <>{children}</>;
  if (checking || !authorized) return <div className="auth-loading">Loading…</div>;
  async function signOut() { try { await api("/api/auth/logout?role=host", { method: "POST" }); } finally { router.replace("/"); } }
  return <div className="app-layout">
    <aside className="sidebar">
      <Link className="brand" href="/host-dashboard"><span className="brand-icon"><Radar size={18} strokeWidth={2.2}/></span><span>proof<span className="brand-dot">.</span><small>HACKATHON JUDGE</small></span></Link>
      <div className="event-chip"><span className="live-dot"/> LIVE EVENT <span className="chip-year">2026</span></div>
      <div className="side-label">WORKSPACE</div>
      <nav className="side-nav">{nav.map(item => { const Icon = item.icon; const active = pathname === item.href || (item.href !== "/host-dashboard" && pathname.startsWith(item.href)); return <Link key={item.href} href={item.href} className={`nav-link ${active ? "active" : ""}`}><Icon size={17}/>{item.label}</Link>; })}</nav>
      <Link className="new-submission" href="/submissions/new"><Plus size={16}/> Add a project</Link>
      <div className="side-spacer"/>
      <div className="rubric-side-card"><div className="rubric-side-heading"><Scale size={15}/> SCORING RUBRIC</div><div className="rubric-side-line"><span>Working functionality</span><b>25%</b></div><div className="rubric-side-line"><span>Problem fit</span><b>20%</b></div><div className="rubric-side-line"><span>Technical complexity</span><b>10%</b></div><div className="rubric-side-line"><span>UI / UX</span><b>10%</b></div><div className="rubric-side-line"><span>Innovation</span><b>25%</b></div><div className="rubric-side-line"><span>Real-world problem</span><b>10%</b></div><div className="rubric-note"><ShieldCheck size={13}/> Scores explain missing evidence</div></div>
      <div className="side-footer"><span className="avatar">H</span><span className="user-label"><b>Host</b><small>Verified account</small></span><button className="signout-btn" onClick={signOut}>Sign out</button></div>
    </aside>
    <main className="main-area"><header className="topbar"><div className="crumb"><span>Hackathon</span><span className="crumb-slash">/</span><b>{pathname.startsWith("/reports") ? "Evaluation report" : pathname.startsWith("/leaderboard") ? "Leaderboard" : pathname.startsWith("/submissions") ? "Projects" : "Overview"}</b></div><div className="topbar-right"><span className="run-status"><Activity size={14}/> Judge engine <b>Ready</b></span></div></header><div className="page-wrap">{children}</div></main>
  </div>;
}
