/**
 * What each wire error code means to a person, and what the UI should do about it.
 *
 * The codes themselves come from `./error-codes.generated.ts`, extracted from the
 * API source. This file supplies the half a generator cannot: the category that
 * decides behaviour, and a sentence worth showing.
 *
 * A code the API can send with no entry here is a **compile** error, not a
 * runtime surprise: the map below is annotated `Record<ApiErrorCode, …>`, so
 * regenerating the codes after the API grows a new one fails the typecheck until
 * the entry is written. That is why there is no separate gap test.
 *
 * Messages never repeat the code and never name an internal component. A learner
 * reading "lexi_render_format_unsupported" learns nothing; "this question could
 * not be shown" at least says what happened to them.
 */

import {
  isKnownApiErrorCode,
  type ApiErrorCode,
} from "./error-codes.generated"

/**
 * How a failure should be handled, independent of which endpoint produced it.
 *
 * - `retryable` — transient. The same request may work shortly; offer retry.
 * - `session_invalidated` — the study session is no longer valid. Leave the
 *   session rather than retrying into the same wall.
 * - `quota` — a deliberate limit was reached. Retrying now cannot help.
 * - `not_found` — the thing addressed is gone. Navigate away, do not retry.
 * - `conflict` — the request contradicts current state. Refresh, then re-decide.
 * - `unauthorized` — credentials are missing, expired, or revoked. Sign in.
 * - `unexpected` — no better classification. Report it and stop.
 */
export type ErrorCategory =
  | "retryable"
  | "session_invalidated"
  | "quota"
  | "not_found"
  | "conflict"
  | "unauthorized"
  | "unexpected"

export interface ErrorTaxonomyEntry {
  category: ErrorCategory
  /** Shown to the learner verbatim. One sentence, no code, no jargon. */
  message: string
}

export const ERROR_TAXONOMY: Record<ApiErrorCode, ErrorTaxonomyEntry> = {
  // --- Authentication and identity -----------------------------------------
  missing_token: {
    category: "unauthorized",
    message: "Sign in to continue.",
  },
  invalid_token: {
    category: "unauthorized",
    message: "Your sign-in is no longer valid. Sign in again.",
  },
  invalid_token_claims: {
    category: "unauthorized",
    message: "Your sign-in is no longer valid. Sign in again.",
  },
  expired_token: {
    category: "unauthorized",
    message: "Your session expired. Sign in again.",
  },
  token_revoked: {
    category: "unauthorized",
    message: "This session was signed out elsewhere. Sign in again.",
  },
  missing_refresh_token: {
    category: "unauthorized",
    message: "Your session expired. Sign in again.",
  },
  invalid_refresh_token: {
    category: "unauthorized",
    message: "Your session expired. Sign in again.",
  },
  oauth_email_not_verified: {
    category: "unauthorized",
    message: "Verify your email with your provider, then sign in again.",
  },
  invalid_redirect_uri: {
    category: "unexpected",
    message: "Sign-in could not start. Try again from the sign-in page.",
  },
  unauthorized: {
    category: "unauthorized",
    message: "Sign in to continue.",
  },
  forbidden: {
    category: "unauthorized",
    message: "You do not have access to this.",
  },
  // The account-deletion guard is raised as an auth error, so it arrives with 401
  // despite being a confirmation problem rather than a credentials one.
  account_delete_confirmation_required: {
    category: "unauthorized",
    message: "Type DELETE exactly to confirm, and sign in again if asked.",
  },

  // --- Hierarchy ------------------------------------------------------------
  node_not_found: {
    category: "not_found",
    message: "That item no longer exists.",
  },
  parent_node_not_found: {
    category: "not_found",
    message: "The destination folder no longer exists.",
  },
  parent_must_be_owned_folder: {
    category: "conflict",
    message: "Items can only go inside a folder you own.",
  },
  node_move_would_create_cycle: {
    category: "conflict",
    message: "A folder cannot be moved inside itself.",
  },
  deck_not_found: {
    category: "not_found",
    message: "That deck no longer exists.",
  },
  deck_senses_require_deck: {
    category: "conflict",
    message: "Words can only be added to a deck.",
  },
  reference_requires_target: {
    category: "conflict",
    message: "Pick the deck this link should point to.",
  },
  reference_must_target_deck: {
    category: "conflict",
    message: "A link can only point at a deck.",
  },
  reference_target_not_found: {
    category: "not_found",
    message: "The linked deck no longer exists.",
  },
  target_only_allowed_for_reference: {
    category: "conflict",
    message: "Only a link can point at another deck.",
  },
  folder_publication_requires_confirmation: {
    category: "conflict",
    message: "Publishing this folder publishes everything inside it. Confirm to continue.",
  },

  // --- Content --------------------------------------------------------------
  sense_not_found: {
    category: "not_found",
    message: "That word is no longer available.",
  },
  word_generation_quota_exceeded: {
    category: "quota",
    message: "You have reached today's limit for adding new words.",
  },

  // --- Study session --------------------------------------------------------
  session_not_found: {
    category: "session_invalidated",
    message: "This study session has ended.",
  },
  session_scope_changed: {
    category: "session_invalidated",
    message: "This deck changed while you were studying, so the session ended.",
  },
  question_not_available: {
    category: "session_invalidated",
    message: "That question is no longer available.",
  },
  question_not_issued_for_session: {
    category: "session_invalidated",
    message: "That question does not belong to this session.",
  },
  question_not_assessable: {
    category: "conflict",
    message: "This card is for reading, not answering.",
  },
  question_preparation_exhausted: {
    category: "retryable",
    message: "Questions could not be prepared just now. Try again in a moment.",
  },
  lexi_question_presentation_invalid: {
    category: "retryable",
    message: "This question could not be shown. Try again in a moment.",
  },
  lexi_render_format_unsupported: {
    category: "retryable",
    message: "This question could not be shown. Try again in a moment.",
  },
  response_not_found: {
    category: "not_found",
    message: "That answer is no longer on record.",
  },
  answer_grading_quota_exceeded: {
    category: "quota",
    message: "You have reached today's limit for graded answers.",
  },
  history_window_invalid: {
    category: "conflict",
    message: "Pick a start date before the end date.",
  },

  // --- Assistant ------------------------------------------------------------
  assistant_not_configured: {
    category: "unexpected",
    message: "The assistant is not available on this deployment.",
  },
  assistant_thread_not_found: {
    category: "not_found",
    message: "That conversation no longer exists.",
  },
  assistant_thread_run_active: {
    category: "conflict",
    message: "Wait for the current reply to finish.",
  },
  assistant_run_not_found: {
    category: "not_found",
    message: "That reply is no longer available.",
  },
  assistant_run_create_conflict: {
    category: "conflict",
    message: "Wait for the current reply to finish.",
  },
  client_message_id_reused: {
    category: "conflict",
    message: "That message was already sent.",
  },
  assistant_message_too_long: {
    category: "conflict",
    message: "That message is too long. Shorten it and send again.",
  },
  assistant_action_not_found: {
    category: "not_found",
    message: "That request is no longer pending.",
  },
  assistant_action_already_resolved: {
    category: "conflict",
    message: "You already answered that request.",
  },
  assistant_action_expired: {
    category: "conflict",
    message: "That request expired. Ask again.",
  },
  assistant_action_not_approved: {
    category: "conflict",
    message: "That action needs your approval first.",
  },
  assistant_action_invalid_arguments: {
    category: "conflict",
    message: "The assistant could not complete that action.",
  },
  assistant_action_stale: {
    category: "conflict",
    message: "Things changed since that request. Ask again.",
  },
  assistant_actor_revoked: {
    category: "unauthorized",
    message: "Your sign-in changed. Sign in again to keep using the assistant.",
  },
  assistant_capacity_exhausted: {
    category: "retryable",
    message: "The assistant is busy. Try again in a moment.",
  },
  assistant_cursor_not_in_collection: {
    category: "not_found",
    message: "That part of the conversation is no longer available.",
  },

  // --- Infrastructure and generic -------------------------------------------
  centrifugo_unavailable: {
    category: "retryable",
    message: "Live updates are unavailable. Your work still saves.",
  },
  core_dependency_unavailable: {
    category: "retryable",
    message: "A service is temporarily unavailable. Try again in a moment.",
  },
  service_unavailable: {
    category: "retryable",
    message: "The service is temporarily unavailable. Try again in a moment.",
  },
  // The catch-all envelope. The API deliberately does not send the underlying
  // exception text, so there is nothing more specific to show — but it is a real
  // server fault, not a user mistake, and saying so is what stops someone
  // re-editing correct input.
  internal_error: {
    category: "retryable",
    message: "Something went wrong on our side. Try again in a moment.",
  },
  // Two writers raced on the same command id. The other one won and its result is
  // authoritative, so a retry of the same command is the wrong move — reloading
  // shows what actually landed.
  async_command_conflict: {
    category: "conflict",
    message: "That request was already handled. Refresh to see the result.",
  },
  // The provider rejected the authorization code exchange. Restarting sign-in is
  // the only recovery; retrying the same callback URL cannot succeed.
  oauth_exchange_failed: {
    category: "unauthorized",
    message: "Sign-in could not be completed. Try signing in again.",
  },
  too_many_requests: {
    category: "quota",
    message: "Too many requests. Wait a moment and try again.",
  },
  payload_too_large: {
    category: "conflict",
    message: "That is too large to send.",
  },
  validation_error: {
    category: "conflict",
    message: "Some of that input is not valid. Check it and try again.",
  },
  bad_request: {
    category: "unexpected",
    message: "That request could not be processed.",
  },
  method_not_allowed: {
    category: "unexpected",
    message: "That request could not be processed.",
  },
  not_found: {
    category: "not_found",
    message: "That could not be found.",
  },
  conflict: {
    category: "conflict",
    message: "That conflicts with the current state. Refresh and try again.",
  },
  http_error: {
    category: "unexpected",
    message: "Something went wrong. Try again.",
  },
}

/** The fallback for a code this build has never heard of. */
const UNKNOWN: ErrorTaxonomyEntry = {
  category: "unexpected",
  message: "Something went wrong. Try again.",
}

/**
 * Classifies a code from a response.
 *
 * Takes a plain string rather than `ApiErrorCode`, because the input is a wire
 * value: a newer API can send a code this build does not know, and that must
 * degrade to a generic message instead of throwing. The code is never shown.
 */
export function classifyErrorCode(code: string): ErrorTaxonomyEntry {
  if (!isKnownApiErrorCode(code)) return UNKNOWN
  return ERROR_TAXONOMY[code] ?? UNKNOWN
}

/** Whether retrying the same request could plausibly succeed. */
export function isRetryable(code: string): boolean {
  return classifyErrorCode(code).category === "retryable"
}
