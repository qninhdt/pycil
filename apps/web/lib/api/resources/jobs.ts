import type { Fetcher } from "../request"

/**
 * One job receipt, as `GET /v1/jobs/{id}` returns it.
 *
 * The vocabulary is the server's: `queued`, `running`, and the three ways a job can
 * stop — `done`, `failed`, `expired`. `expired` is not a failure the learner caused
 * and not a success either: the receipt outlived its TTL, so the only honest thing to
 * say is that the outcome is unknown and the work can be retried.
 */
export interface JobSnapshot {
  jobId: string
  kind: string
  status: "queued" | "running" | "done" | "failed" | "expired"
  result: Record<string, unknown> | null
  errorCode: string | null
}

export function jobsResource(fetch: Fetcher) {
  return {
    get: (jobId: string) => fetch<JobSnapshot>(`/v1/jobs/${jobId}`),
  }
}
