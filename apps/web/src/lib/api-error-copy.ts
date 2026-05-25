import type { ApiError } from "@/lib/api-client/base";

const COPY_BY_CODE: Record<string, string> = {
  term_empty: "Term cannot be empty",
  term_too_long: "Term is too long",
  term_control_chars: "Term has invalid characters",
  rate_limited: "Hold on — 5 enrichments per hour",
  budget_exhausted: "Daily budget reached, try tomorrow",
  csrf_mismatch: "Session expired, refresh the page",
  deck_not_found: "Deck not found",
  deck_forbidden: "You don't have access to this deck",
  node_not_deck: "This node is not a deck",
  unauthorized: "Please sign in again",
  session_revoked: "Session revoked, sign in again",
  invalid_session: "Session is invalid, sign in again",
  expired_session: "Session expired, sign in again",
};

export function apiErrorMessage(error: unknown, fallback = "Something went wrong"): string {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  const err = error as Partial<ApiError> & { message?: string };
  if (err.code && COPY_BY_CODE[err.code]) return COPY_BY_CODE[err.code];
  return err.message ?? fallback;
}
