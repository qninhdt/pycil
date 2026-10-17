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
    super(
      status === 401
        ? 'Your session has expired. Sign in again.'
        : code === 'job_failed'
          ? 'This request could not be completed. Please retry.'
          : code === 'job_wait_timeout'
            ? 'This job is taking longer than expected. Return later to check its result.'
            : code === 'job_not_found'
              ? 'This job has expired or is no longer available. Please submit again.'
              : code === 'scope_too_large'
          ? 'This Library is too large to calculate at once. Open a smaller folder or deck.'
          : code === 'reference_unavailable'
            ? 'This reference is no longer available.'
            : code === 'question_generation_unavailable'
              ? 'Questions could not be generated right now. Retry to prepare your session.'
              : code === 'grading_unavailable'
                ? 'Your answer could not be checked right now. Retry without changing your answer.'
                : code === 'node_not_found'
                  ? 'This material could not be found.'
                  : code === 'invalid_cursor'
                    ? 'This page is no longer available. Return to the first page.'
                    : code === 'handle_unavailable'
                      ? 'This handle is already taken. Choose another handle.'
                      : code === 'invalid_handle'
                        ? 'Use 3–30 lowercase letters, numbers or underscores, starting with a letter.'
                        : code === 'node_cycle'
                          ? 'Choose a destination outside this folder and its contents.'
                          : code === 'quota_exceeded' || code === 'deck_sense_limit_exceeded'
                            ? 'This change exceeds your Library limit. Remove some material or choose a smaller selection.'
                            : code === 'publication_confirmation_required'
                              ? 'Confirm that this material will be publicly readable.'
                              : code === 'private_reference_cannot_be_published'
                                ? 'This material references a private source. Publish the source or remove that reference first.'
                                : status === 429
                                  ? 'Too many requests. Wait a moment, then retry.'
                                  : code === 'invalid_response'
                                    ? 'The server returned incomplete data. Please retry.'
                                    : status === 422
                                      ? 'This selection could not be prepared. Check your learning settings or choose a smaller scope.'
                                      : 'Could not load this information. Check your connection and retry.',
    )
  }
}

