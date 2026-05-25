"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, CheckCircle, AlertCircle } from "lucide-react";
import { useJobStream } from "@/lib/api-hooks/use-jobs";
import { queryKeys } from "@/lib/api-client/query-keys";
import type { UUID } from "@/types/domain";

interface JobStreamWatcherProps {
  jobId: string;
  deckId: UUID;
  onCompleted?: () => void;
  onFailed?: (error: string | null) => void;
}

export function JobStreamWatcher({
  jobId,
  deckId,
  onCompleted,
  onFailed,
}: JobStreamWatcherProps) {
  const stream = useJobStream(jobId);
  const qc = useQueryClient();

  useEffect(() => {
    if (stream.status === "completed") {
      qc.invalidateQueries({ queryKey: queryKeys.deck.terms(deckId) });
      qc.invalidateQueries({ queryKey: queryKeys.nodes.detail(deckId) });
      onCompleted?.();
    } else if (stream.status === "failed") {
      onFailed?.(stream.error);
    }
  }, [stream.status, stream.error, qc, deckId, onCompleted, onFailed]);

  if (stream.status === "completed") {
    return (
      <div className="flex items-center gap-2 text-sm text-emerald-600">
        <CheckCircle className="h-4 w-4" />
        Definitions ready
      </div>
    );
  }
  if (stream.status === "failed") {
    return (
      <div className="flex items-start gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4 mt-0.5" />
        <span>{stream.error ?? "Generation failed"}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      Generating definitions…
    </div>
  );
}
