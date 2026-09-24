/**
 * Every error code the API can put on the wire, with the HTTP statuses it can
 * arrive with. A code appears under more than one status when it is raised from
 * more than one error class.
 *
 * Maintained by hand alongside the API's error classes, and checked against them
 * by `apps/api/tests/unit/architecture/test_web_error_codes_match_api.py`. That
 * check is what keeps this honest: the two halves of the repository share no type
 * system, so a code added or renamed on the server would otherwise leave this map
 * quietly stale, and every real failure would fall through `classifyErrorCode` to
 * a generic "something went wrong" with no retry offered.
 */
export const API_ERROR_STATUS = {
  // --- Authentication and identity -----------------------------------------
  "account_delete_confirmation_required": [401],
  "account_not_found": [404],
  "auth_not_configured": [401],
  "clerk_deletion_failed": [503],
  "clerk_not_configured": [503],
  "expired_token": [401],
  "forbidden": [403],
  "identity_conflict": [409],
  "invalid_authorization": [401],
  "invalid_token": [401],
  "invalid_token_claims": [401],
  "missing_token": [401],
  "unauthorized": [401],
  "user_provisioning_failed": [401],

  // --- Hierarchy ------------------------------------------------------------
  "deck_not_found": [404],
  "deck_senses_require_deck": [409],
  "folder_publication_requires_confirmation": [409],
  "node_depth_exceeded": [409],
  "node_move_would_create_cycle": [409],
  "node_not_found": [404],
  "parent_must_be_owned_folder": [409],
  "parent_node_not_found": [404],
  "reference_must_target_deck_or_folder": [409],
  "reference_requires_target": [409],
  "reference_target_not_found": [404],
  "target_only_allowed_for_reference": [409],

  // --- Content --------------------------------------------------------------
  "sense_not_found": [404],

  // --- Study session and learning -------------------------------------------
  "free_text_grade_timeout": [503],
  "free_text_grade_unavailable": [503],
  "history_window_invalid": [409],
  "lexi_question_presentation_invalid": [503],
  "lexi_render_format_unsupported": [503],
  "question_not_assessable": [409],
  "question_not_available": [409],
  "question_not_issued_for_session": [409],
  "question_preparation_exhausted": [503],
  "question_submission_in_progress": [409],
  "reask_delivery_id_missing": [409],
  "response_not_found": [404],
  "response_not_ready": [409],
  "sense_already_graded": [409],
  "session_not_found": [404],
  "session_scope_changed": [409],
  "study_session_changed": [409],
  "study_session_claim_lost": [409],
  "study_session_schema_unsupported": [409],

  // --- Credits --------------------------------------------------------------
  "assistant_usage_regressed": [409],
  "credit_debit_amount_mismatch": [409],
  "credit_debit_reference_reused": [409],
  "credit_exhausted": [409],

  // --- Assistant ------------------------------------------------------------
  "assistant_actor_revoked": [403],
  "assistant_cursor_not_in_collection": [404],
  "assistant_message_too_long": [413],
  "assistant_metering_state_invalid": [503],
  "assistant_not_configured": [503],
  "assistant_run_id_reused": [409],
  "assistant_run_not_resumable": [409],
  "assistant_thread_not_found": [404],
  "assistant_turn_in_progress": [409],
  "assistant_turn_lease_lost": [409],

  // --- Jobs -----------------------------------------------------------------
  "job_not_found": [404],

  // --- Infrastructure and generic -------------------------------------------
  "bad_request": [400],
  "conflict": [409],
  "core_dependency_unavailable": [503],
  "http_error": [422],
  "internal_error": [500],
  "method_not_allowed": [405],
  "not_found": [404],
  "payload_too_large": [413],
  "service_unavailable": [503],
  "too_many_requests": [429],
  "validation_error": [422],
} as const

export type ApiErrorCode = keyof typeof API_ERROR_STATUS

export function isKnownApiErrorCode(code: string): code is ApiErrorCode {
  return code in API_ERROR_STATUS
}
