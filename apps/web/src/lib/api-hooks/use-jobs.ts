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
  status: JobStatus | "idle" | "failed";
  result: JobRow["result"] | null;
  error: string | null;
  attempts: number;
}

const SSE_DELAYS_MS = [1000, 2000, 5000, 10000, 30000];
const SSE_MAX_ATTEMPTS = 6;
const SSE_COOLDOWN_MS = 5 * 60 * 1000;

function _attemptKey(jobId: string) {
  return `sse-attempt:${jobId}`;
}

function _readAttempts(jobId: string): number {
  if (typeof sessionStorage === "undefined") return 0;
  const raw = sessionStorage.getItem(_attemptKey(jobId));
  if (!raw) return 0;
  const [n, ts] = raw.split("|");
  if (!n || !ts) return 0;
  if (Date.now() - Number(ts) > SSE_COOLDOWN_MS) return 0;
  return Math.max(0, Number(n) || 0);
}

function _writeAttempts(jobId: string, n: number): void {
  if (typeof sessionStorage === "undefined") return;
  sessionStorage.setItem(_attemptKey(jobId), `${n}|${Date.now()}`);
}

function _clearAttempts(jobId: string): void {
  if (typeof sessionStorage === "undefined") return;
  sessionStorage.removeItem(_attemptKey(jobId));
}

export function useJobStream(jobId: string | null | undefined) {
  const [state, setState] = useState<JobStreamState>({
    status: "idle",
    result: null,
    error: null,
    attempts: 0,
  });
  const sourceRef = useRef<EventSource | null>(null);
  const retryRef = useRef<number | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;

    const open = (attempt: number) => {
      if (cancelled) return;
      const url = jobsApi.jobStreamUrl(jobId);
      const source = new EventSource(url, { withCredentials: true });
      sourceRef.current = source;

      const onStatus = (event: MessageEvent<string>) => {
        try {
          const payload = JSON.parse(event.data) as Partial<JobRow>;
          const status = (payload.status as JobStatus) ?? "running";
          setState({
            status,
            result: (payload.result ?? null) as JobRow["result"] | null,
            error: payload.error ?? null,
            attempts: attempt,
          });
          if (status === "completed" || status === "failed") {
            _clearAttempts(jobId);
            source.close();
          }
        } catch {
          // ignore malformed frames
        }
      };

      source.addEventListener("status", onStatus as EventListener);
      source.addEventListener("timeout", () => source.close());
      source.onerror = () => {
        source.close();
        if (cancelled) return;
        const next = attempt + 1;
        if (next >= SSE_MAX_ATTEMPTS) {
          // Don't refresh timestamp — let the existing 5-min cool-down expire
          // so the user gets a fresh budget after they walk away.
          setState((s) => ({
            ...s,
            status: "failed",
            error: "stream_failed",
            attempts: next,
          }));
          return;
        }
        _writeAttempts(jobId, next);
        const base = SSE_DELAYS_MS[Math.min(next - 1, SSE_DELAYS_MS.length - 1)];
        const delay = base + Math.random() * base * 0.3;
        retryRef.current = window.setTimeout(() => open(next), delay);
      };
    };

    open(_readAttempts(jobId));

    return () => {
      cancelled = true;
      if (retryRef.current !== null) {
        window.clearTimeout(retryRef.current);
        retryRef.current = null;
      }
      sourceRef.current?.close();
      sourceRef.current = null;
    };
  }, [jobId]);

  return state;
}
