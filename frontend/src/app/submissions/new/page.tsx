import Link from "next/link";
import { ArrowLeft, ArrowRight, FileText } from "lucide-react";

export default function NewSubmissionPage(){
  return <><div className="eyebrow">PARTICIPANT REGISTRATIONS</div><h1 className="page-title" style={{marginTop:8}}>Upload participant responses</h1><p className="page-subtitle">Import participant details from a searchable PDF, CSV, or Excel file.</p><section className="panel" style={{maxWidth:620,marginTop:18}}><div className="panel-title">Registration file requirements</div><p className="participant-copy">Include a participant name and email address. Phone number is saved when provided. Participants sign in with Google using the roster email; their project submissions are routed to the host who uploaded that roster.</p><div style={{display:"flex",gap:9,flexWrap:"wrap",marginTop:16}}><Link href="/host-dashboard#participant-registrations" className="primary-btn">Go to participant registrations <ArrowRight size={14}/></Link><Link href="/submissions" className="secondary-btn"><ArrowLeft size={14}/> Back to projects</Link></div></section></>;
}
