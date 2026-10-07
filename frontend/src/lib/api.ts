// In production, prefer a same-origin /api rewrite (API_PROXY_TARGET in
// next.config.ts). This keeps OAuth cookies first-party on Vercel. Local Docker
// continues to call the API directly at localhost:8000.
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? (process.env.NODE_ENV === "development" ? "http://localhost:8000" : "");

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { ...options, credentials: "include", headers: { "Content-Type": "application/json", ...(options?.headers || {}) }, cache: "no-store" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const body = await response.json(); message = body.detail || message; } catch { /* keep status fallback */ }
    throw new Error(message);
  }
  return response.json();
}

export async function upload<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { method: "POST", body, credentials: "include", cache: "no-store" });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try { const detail = await response.json(); message = detail.detail || message; } catch { /* use fallback */ }
    throw new Error(message);
  }
  return response.json();
}

export type Run = {
  id: string; submission_id: string; status: string; phase: string; progress: number; total_score: number | null; confidence: number | null;
  report: any; observations: any[]; evidence: any[]; review_flags: string[]; error_message: string | null; created_at: string; completed_at: string | null;
};
export type Submission = { id: string; application_number: string | null; project_name: string; participant_names: string[]; deployed_url: string; problem_statement: string; solution_description: string; source_pdf_available: boolean; github_url: string | null; ai_tools_metadata: string[]; created_at: string; latest_run: Run | null };
export type Leader = { rank: number; submission_id: string; application_number: string | null; project_name: string; participant_names: string[]; total_score: number; confidence: number; needs_review: boolean; run_id: string };
export type ParticipantDetails = { linked: boolean; application_number: string | null; project_name: string; participant_name: string; phone: string; email: string; college_name: string; problem_statement: string; solution_description: string; deployed_url: string; github_url: string | null; has_submission: boolean; evaluation_status: string; total_score: number | null; confidence: number | null; report: any | null };
export const dateLabel = (value?: string | null) => value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—";
