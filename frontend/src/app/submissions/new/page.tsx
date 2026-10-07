import Link from "next/link";
import { ArrowLeft, ArrowRight, FileText } from "lucide-react";

export default function NewSubmissionPage(){
  return <><div className="eyebrow">PARTICIPANT REGISTRATIONS</div><h1 className="page-title" style={{marginTop:8}}>Upload participant responses</h1><p className="page-subtitle">The host uploader reads the full response table and imports all rows from one PDF.</p><section className="panel" style={{maxWidth:620,marginTop:18}}><div className="panel-title">Use the registration uploader</div><p className="participant-copy">The PDF should have columns for <b>Name</b>, <b>Phone Number</b>, and <b>Email</b>. The host dashboard extracts each row and assigns an ID. If an email is clipped in the PDF, that participant can still link using the ID shared by the host.</p><div style={{display:"flex",gap:9,flexWrap:"wrap",marginTop:16}}><Link href="/host-dashboard#participant-registrations" className="primary-btn">Go to participant registrations <ArrowRight size={14}/></Link><Link href="/submissions" className="secondary-btn"><ArrowLeft size={14}/> Back to projects</Link></div></section></>;
}
