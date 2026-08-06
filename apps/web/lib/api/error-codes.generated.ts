/**
 * Generated from apps/api by scripts/extract-error-codes.py. Do not edit.
 *
 * Source revision: 8b0178a
 *
 * Every error code the API can put on the wire, with the HTTP statuses it can
 * arrive with. A code appears under more than one status when it is raised from
 * more than one error class.
 *
 * Regenerate with:  cd apps/api && uv run python ../../scripts/extract-error-codes.py
 */

export const API_ERROR_STATUS = {
  "account_delete_confirmation_required": [401],
  "answer_grading_quota_exceeded": [409],
  "assistant_action_already_resolved": [409],
  "assistant_action_expired": [409],
  "assistant_action_invalid_arguments": [409],
  "assistant_action_not_approved": [409],
  "assistant_action_not_found": [404],
  "assistant_action_stale": [409, 503],
  "assistant_actor_revoked": [403],
  "assistant_capacity_exhausted": [409],
  "assistant_cursor_not_in_collection": [404],
  "assistant_message_too_long": [503],
  "assistant_not_configured": [503],
  "assistant_run_create_conflict": [409],
  "assistant_run_not_found": [404, 409],
  "assistant_thread_not_found": [404],
  "assistant_thread_run_active": [409],
  "async_command_conflict": [409],
  "bad_request": [400],
  "centrifugo_unavailable": [503],
  "client_message_id_reused": [409],
  "conflict": [409],
  "core_dependency_unavailable": [503],
  "deck_not_found": [404],
  "deck_senses_require_deck": [409],
  "expired_token": [401],
  "folder_publication_requires_confirmation": [409],
  "forbidden": [403],
  "history_window_invalid": [409],
  "http_error": [500],
  "internal_error": [500],
  "invalid_redirect_uri": [400],
  "invalid_refresh_token": [401],
  "invalid_token": [401],
  "invalid_token_claims": [401],
  "lexi_question_presentation_invalid": [503],
  "lexi_render_format_unsupported": [503],
  "method_not_allowed": [405],
  "missing_refresh_token": [401],
  "missing_token": [401],
  "node_move_would_create_cycle": [409],
  "node_not_found": [404],
  "not_found": [404],
  "oauth_email_not_verified": [401],
  "oauth_exchange_failed": [401],
  "parent_must_be_owned_folder": [409],
  "parent_node_not_found": [404],
  "payload_too_large": [413, 500],
  "question_not_assessable": [409],
  "question_not_available": [409],
  "question_not_issued_for_session": [409],
  "question_preparation_exhausted": [503],
  "reference_must_target_deck": [409],
  "reference_requires_target": [409],
  "reference_target_not_found": [404],
  "response_not_found": [404],
  "sense_not_found": [404],
  "service_unavailable": [503],
  "session_not_found": [404],
  "session_scope_changed": [409],
  "target_only_allowed_for_reference": [409],
  "token_revoked": [401],
  "too_many_requests": [429],
  "unauthorized": [401],
  "validation_error": [422],
  "word_generation_quota_exceeded": [429],
} as const

export type ApiErrorCode = keyof typeof API_ERROR_STATUS

export const API_ERROR_CODES = Object.keys(API_ERROR_STATUS) as ApiErrorCode[]

export function isKnownApiErrorCode(code: string): code is ApiErrorCode {
  return code in API_ERROR_STATUS
}
