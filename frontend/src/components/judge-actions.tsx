"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Props = { submissionId: string; onComplete: () => Promise<void> };

export function JudgeActions({ submissionId, onComplete }: Props) {
  const [busy, setBusy] = useState<"evaluate" | "reevaluate" | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(""), 5000);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  async function start(action: "evaluate" | "reevaluate") {
    setBusy(action);
    setError("");
    try {
      await api(`/api/submissions/${submissionId}/judge`, { method: "POST" });
      await onComplete();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not start evaluation.";
      if (action === "reevaluate" && message.includes("still active")) {
        setNotice(message);
      } else if (action === "reevaluate" && message.includes("waiting for a judge worker")) {
        setNotice(message);
      } else {
        setError(message);
      }
    } finally {
      setBusy(null);
    }
  }

  return <div className="judge-actions">
    <button className="primary-btn" type="button" disabled={busy !== null} onClick={() => start("evaluate")}>
      {busy === "evaluate" ? "Starting…" : "Evaluate"}
    </button>
    <button className="secondary-btn" type="button" disabled={busy !== null} onClick={() => start("reevaluate")}>
      {busy === "reevaluate" ? "Starting…" : "Re-evaluate"}
    </button>
    {error && <span className="judge-action-error">{error}</span>}
    {notice && <div className="judge-popup" role="alert" aria-live="assertive">
      <span>{notice}</span>
      <button type="button" aria-label="Dismiss message" onClick={() => setNotice("")}>×</button>
    </div>}
  </div>;
}
