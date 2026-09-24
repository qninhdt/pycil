/**
 * What each wire error code means to a person, and what the UI should do about it.
 *
 * The codes themselves come from `./error-codes.ts`, mirroring the API's error
 * classes. This file supplies what the code list cannot: the category that
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
} from "./error-codes"

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
  // A malformed `Authorization` header — not a bearer scheme, or a second
  // credential smuggled into the same value. Clerk's SDK mints a correct one, so
  // this is a hand-built request rather than a stale session; signing in again is
  // still the recovery a person can act on.
  invalid_authorization: {
    category: "unauthorized",
    message: "Sign in to continue.",
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
  // Provisioning lost a race and the row is still absent. Signing in again is the
  // retry, which is why this is not simply "your sign-in is invalid".
  user_provisioning_failed: {
    category: "retryable",
    message: "Your account could not be set up. Sign in again in a moment.",
  },
  // Another Clerk subject already holds this email. Linking them would hand one
  // learner's library to another, so the refusal is permanent for this identity.
  identity_conflict: {
    category: "conflict",
    message: "That email is already linked to a different account. Sign in with the original one.",
  },
  // Deployment configuration, not a learner action. Retrying cannot help, and
  // neither can signing in.
  auth_not_configured: {
    category: "unexpected",
    message: "Sign-in is not available on this deployment.",
  },
  clerk_not_configured: {
    category: "unexpected",
    message: "Account deletion is not available on this deployment.",
  },
  // Clerk's own API rejected the delete. Retrying is the one thing that can help.
  clerk_deletion_failed: {
    category: "retryable",
    message: "Your account could not be deleted just now. Try again in a moment.",
  },
  account_not_found: {
    category: "not_found",
    message: "Your account could not be found.",
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
  node_depth_exceeded: {
    category: "conflict",
    message: "Folders can only be nested so deep. Move this item somewhere shallower.",
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
    message: "Pick the deck or folder this link should point to.",
  },
  // A link to another link would be an indirection the resolver cannot bound, and
  // a link to itself is meaningless.
  reference_must_target_deck_or_folder: {
    category: "conflict",
    message: "A link can only point at a deck or a folder.",
  },
  reference_target_not_found: {
    category: "not_found",
    message: "The linked item no longer exists.",
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

  // --- Study session and learning -------------------------------------------
  session_not_found: {
    category: "session_invalidated",
    message: "This study session has ended.",
  },
  session_scope_changed: {
    category: "session_invalidated",
    message: "This deck changed while you were studying, so the session ended.",
  },
  // The stored session document is a version this build cannot read, which a
  // rollout can produce. The document is per-session, so starting a new one works.
  study_session_schema_unsupported: {
    category: "session_invalidated",
    message: "This study session can no longer be read. Start a new one.",
  },
  // Another writer changed the session document underneath this request, so the
  // answer that was already committed is no longer the head of this session.
  study_session_claim_lost: {
    category: "session_invalidated",
    message: "This session moved on while your answer was being saved.",
  },
  // A concurrent write lost its compare-and-swap. The session itself is intact,
  // so the learner retries into the current state rather than losing the session.
  study_session_changed: {
    category: "conflict",
    message: "This session was updated elsewhere. Try again.",
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
  // A second submit for one question while the first still holds its claim. The
  // claim expires on its own, so the answer is not lost — only early.
  question_submission_in_progress: {
    category: "conflict",
    message: "That answer is still being marked. Wait a moment.",
  },
  // The duplicate this guard exists to refuse: a second *graded* answer for one
  // sense in one session. A re-ask is the opposite case and does not arrive here.
  sense_already_graded: {
    category: "conflict",
    message: "You have already answered this card in this session.",
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
  free_text_grade_timeout: {
    category: "retryable",
    message: "Marking that answer took too long. Try again in a moment.",
  },
  free_text_grade_unavailable: {
    category: "retryable",
    message: "That answer could not be marked just now. Try again in a moment.",
  },
  response_not_found: {
    category: "not_found",
    message: "That answer is no longer on record.",
  },
  // The response row has no id after being flushed, which is an internal
  // invariant rather than anything the learner did.
  response_not_ready: {
    category: "unexpected",
    message: "That answer could not be recorded. Try again.",
  },
  // An ungraded re-ask reached settlement without the delivery id that keys its
  // charge. Nothing the learner can act on.
  reask_delivery_id_missing: {
    category: "unexpected",
    message: "That card could not be re-asked. Continue to the next one.",
  },
  history_window_invalid: {
    category: "conflict",
    message: "Pick a start date before the end date.",
  },

  // --- Credits --------------------------------------------------------------
  // The only admission gate left is an assistant turn: exhausted credit degrades
  // the learning path rather than refusing it, so this cannot arrive from study.
  credit_exhausted: {
    category: "quota",
    message: "You have used your credits for this month. They renew at the start of the next one.",
  },
  // Accounting invariants: a reference id must be settled once, by one owner, for
  // one amount. A disagreement means the ledger is inconsistent, not that the
  // learner did something wrong.
  credit_debit_reference_reused: {
    category: "unexpected",
    message: "That charge could not be recorded. Contact support if it persists.",
  },
  credit_debit_amount_mismatch: {
    category: "unexpected",
    message: "That charge could not be recorded. Contact support if it persists.",
  },
  assistant_usage_regressed: {
    category: "unexpected",
    message: "That turn's usage could not be recorded. Contact support if it persists.",
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
  assistant_cursor_not_in_collection: {
    category: "not_found",
    message: "That part of the conversation is no longer available.",
  },
  // One active turn per account is a consistency boundary for billing, not a
  // paid-tier limit: a second turn is refused, not downgraded.
  assistant_turn_in_progress: {
    category: "conflict",
    message: "Wait for the current reply to finish.",
  },
  // The lease was lost mid-stream, which means another turn for this account took
  // it. The interrupted reply is not recoverable.
  assistant_turn_lease_lost: {
    category: "conflict",
    message: "This reply stopped because the same account started another one.",
  },
  // A run id that already has a saved turn. The earlier result is authoritative,
  // so re-sending is the wrong move — reloading shows what actually landed.
  assistant_run_id_reused: {
    category: "conflict",
    message: "That request was already handled. Refresh to see the result.",
  },
  // The run completed or failed, or its checkpoint holds no interrupt to answer.
  assistant_run_not_resumable: {
    category: "conflict",
    message: "That reply can no longer be continued.",
  },
  // The pending metering record for a turn is unreadable, so the turn cannot be
  // settled. Retrying the same settlement fails the same way.
  assistant_metering_state_invalid: {
    category: "unexpected",
    message: "That turn could not be settled. Start a new one.",
  },
  assistant_message_too_long: {
    category: "conflict",
    message: "That message is too long. Shorten it and send again.",
  },
  assistant_actor_revoked: {
    category: "unauthorized",
    message: "Your sign-in changed. Sign in again to keep using the assistant.",
  },

  // --- Jobs -----------------------------------------------------------------
  // Also the answer for another learner's job, deliberately: distinguishing the
  // two would let a caller enumerate job ids.
  job_not_found: {
    category: "not_found",
    message: "That job is no longer available.",
  },

  // --- Infrastructure and generic -------------------------------------------
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
