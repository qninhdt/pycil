import type { UUID } from "./node";

/** Returned by submit/check when an answer needs async (LLM) grading. */
export interface AsyncGradePending {
  grading: "pending";
  job_id: UUID;
  response_id: UUID;
}

/** Body for the apply-verdict endpoint, called after the SSE verdict resolves. */
export interface ApplyVerdictRequest {
  response_id: UUID;
}

export function isAsyncGradePending(
  value: unknown
): value is AsyncGradePending {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as { grading?: unknown }).grading === "pending"
  );
}
