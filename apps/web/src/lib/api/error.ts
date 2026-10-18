export interface InvalidParam {
  name: string
  reason: string
}

export interface ProblemDetailsPayload {
  type?: string
  title?: string
  status?: number
  detail?: string
  instance?: string
  code?: string
  request_id?: string
  invalid_params?: InvalidParam[]
  error?: string
}

export function resolveApiErrorMessage(status: number, code: string): string {
  if (status === 401) {
    return 'Your session has expired. Sign in again.'
  }
  switch (code) {
    case 'job_failed':
      return 'This request could not be completed. Please retry.'
    case 'job_wait_timeout':
      return 'This job is taking longer than expected. Return later to check its result.'
    case 'job_not_found':
      return 'This job has expired or is no longer available. Please submit again.'
    case 'scope_too_large':
      return 'This Library is too large to calculate at once. Open a smaller folder or deck.'
    case 'reference_unavailable':
      return 'This reference is no longer available.'
    case 'question_generation_unavailable':
      return 'Questions could not be generated right now. Retry to prepare your session.'
    case 'grading_unavailable':
      return 'Your answer could not be checked right now. Retry without changing your answer.'
    case 'node_not_found':
      return 'This material could not be found.'
    case 'invalid_cursor':
      return 'This page is no longer available. Return to the first page.'
    case 'handle_unavailable':
      return 'This handle is already taken. Choose another handle.'
    case 'invalid_handle':
      return 'Use 3–30 lowercase letters, numbers or underscores, starting with a letter.'
    case 'node_cycle':
      return 'Choose a destination outside this folder and its contents.'
    case 'quota_exceeded':
    case 'deck_sense_limit_exceeded':
      return 'This change exceeds your Library limit. Remove some material or choose a smaller selection.'
    case 'publication_confirmation_required':
      return 'Confirm that this material will be publicly readable.'
    case 'private_reference_cannot_be_published':
      return 'This material references a private source. Publish the source or remove that reference first.'
  }
  if (status === 429) {
    return 'Too many requests. Wait a moment, then retry.'
  }
  if (code === 'invalid_response') {
    return 'The server returned incomplete data. Please retry.'
  }
  if (status === 422) {
    return 'This selection could not be prepared. Check your learning settings or choose a smaller scope.'
  }
  return 'Could not load this information. Check your connection and retry.'
}

export class ApiError extends Error {
  retryAfterSeconds?: number
  constructor(
    public status: number,
    public code: string,
    public detail?: string,
    public requestId?: string,
    public instance?: string,
    public invalidParams?: InvalidParam[],
  ) {
    super(resolveApiErrorMessage(status, code))
  }
}
