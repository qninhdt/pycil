"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import * as jobsApi from "@/lib/api-client/jobs";
import { queryKeys } from "@/lib/api-client/query-keys";
import type { JobRow, JobStatus } from "@/types/domain";

export function useJob(id: string | null | undefined) {
  return useQuery({
    queryKey: id ? queryKeys.job(id) : queryKeys.job("__none"),
    queryFn: () => jobsApi.getJob(id as string),
    enabled: !!id,
  });
}

export interface JobStreamState {
  status: JobStatus | "idle";
  result: JobRow["result"] | null;
  error: string | null;
}

export function useJobStream(jobId: string | null | undefined) {
  const [state, setState] = useState<JobStreamState>({
    status: "idle",
    result: null,
    error: null,
  });
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;
    const url = jobsApi.jobStreamUrl(jobId);
    const source = new EventSource(url, { withCredentials: true });
    sourceRef.current = source;

    const onStatus = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as Partial<JobRow>;
        setState({
          status: (payload.status as JobStatus) ?? "running",
          result: (payload.result ?? null) as JobRow["result"] | null,
          error: payload.error ?? null,
        });
        if (payload.status === "completed" || payload.status === "failed") {
          source.close();
        }
      } catch {
        // ignore malformed frames
      }
    };

    source.addEventListener("status", onStatus as EventListener);
    source.addEventListener("timeout", () => source.close());
    source.onerror = () => {
      // Allow reconnection logic later; close + surface for now.
      setState((s) => (s.status === "idle" ? { ...s, status: "running" } : s));
    };

    return () => {
      source.close();
      sourceRef.current = null;
    };
  }, [jobId]);

  return state;
}
