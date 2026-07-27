"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { confirmActionAction } from "@/lib/actions/assistant";

interface HitlActionCardProps {
  threadId: string;
  actionId: string;
  description: string;
  warning?: string;
  onDecisionComplete?: (decision: "approve" | "reject") => void;
}

export function HitlActionCard({
  threadId,
  actionId,
  description,
  warning,
  onDecisionComplete,
}: HitlActionCardProps) {
  const [status, setStatus] = useState<"idle" | "loading" | "approved" | "rejected">("idle");

  async function handleDecision(decision: "approve" | "reject") {
    setStatus("loading");
    const ok = await confirmActionAction(threadId, actionId, decision);
    if (ok) {
      setStatus(decision === "approve" ? "approved" : "rejected");
      if (onDecisionComplete) {
        onDecisionComplete(decision);
      }
    } else {
      setStatus("idle");
    }
  }

  if (status === "approved") {
    return (
      <div className="my-3 p-4 rounded-xl border border-emerald-200 bg-emerald-50 dark:bg-emerald-950/40 dark:border-emerald-900 flex items-center gap-3">
        <CheckCircle2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 shrink-0" />
        <p className="text-sm font-medium text-emerald-900 dark:text-emerald-200">
          Action Approved: {description}
        </p>
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div className="my-3 p-4 rounded-xl border border-neutral-200 bg-neutral-100 dark:bg-neutral-800/50 dark:border-neutral-700 flex items-center gap-3">
        <XCircle className="w-5 h-5 text-neutral-500 dark:text-neutral-400 shrink-0" />
        <p className="text-sm font-medium text-neutral-600 dark:text-neutral-400">
          Action Cancelled: {description}
        </p>
      </div>
    );
  }

  return (
    <div className="my-3 p-5 rounded-2xl border border-amber-200 bg-amber-50/70 dark:bg-amber-950/40 dark:border-amber-800 shadow-sm space-y-3">
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/50 text-amber-700 dark:text-amber-300">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <div>
          <h4 className="text-sm font-semibold text-amber-950 dark:text-amber-100">
            Human Approval Required
          </h4>
          <p className="mt-0.5 text-sm text-amber-900 dark:text-amber-200">
            {description}
          </p>
          {warning && (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-400 italic">
              Note: {warning}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2 pt-2 border-t border-amber-200/60 dark:border-amber-800/60">
        <button
          type="button"
          disabled={status === "loading"}
          onClick={() => handleDecision("reject")}
          className="px-4 py-2 rounded-xl border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-200/50 dark:hover:bg-neutral-800 text-sm font-medium text-neutral-700 dark:text-neutral-200 transition-colors disabled:opacity-50"
        >
          Cancel / Reject
        </button>
        <button
          type="button"
          disabled={status === "loading"}
          onClick={() => handleDecision("approve")}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium shadow-sm transition-colors disabled:opacity-50"
        >
          {status === "loading" && <Loader2 className="w-4 h-4 animate-spin" />}
          Approve Action
        </button>
      </div>
    </div>
  );
}
