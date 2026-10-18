import { describe, expect, test } from 'vitest'
import { ApiError, resolveApiErrorMessage } from '../../src/lib/api/error'

describe('resolveApiErrorMessage and ApiError message translation', () => {
  const cases: [status: number, code: string, expectedMessage: string][] = [
    [401, 'unauthorized', 'Your session has expired. Sign in again.'],
    [401, 'job_failed', 'Your session has expired. Sign in again.'],
    [500, 'job_failed', 'This request could not be completed. Please retry.'],
    [504, 'job_wait_timeout', 'This job is taking longer than expected. Return later to check its result.'],
    [404, 'job_not_found', 'This job has expired or is no longer available. Please submit again.'],
    [400, 'scope_too_large', 'This Library is too large to calculate at once. Open a smaller folder or deck.'],
    [404, 'reference_unavailable', 'This reference is no longer available.'],
    [503, 'question_generation_unavailable', 'Questions could not be generated right now. Retry to prepare your session.'],
    [503, 'grading_unavailable', 'Your answer could not be checked right now. Retry without changing your answer.'],
    [404, 'node_not_found', 'This material could not be found.'],
    [400, 'invalid_cursor', 'This page is no longer available. Return to the first page.'],
    [409, 'handle_unavailable', 'This handle is already taken. Choose another handle.'],
    [400, 'invalid_handle', 'Use 3–30 lowercase letters, numbers or underscores, starting with a letter.'],
    [400, 'node_cycle', 'Choose a destination outside this folder and its contents.'],
    [403, 'quota_exceeded', 'This change exceeds your Library limit. Remove some material or choose a smaller selection.'],
    [403, 'deck_sense_limit_exceeded', 'This change exceeds your Library limit. Remove some material or choose a smaller selection.'],
    [400, 'publication_confirmation_required', 'Confirm that this material will be publicly readable.'],
    [400, 'private_reference_cannot_be_published', 'This material references a private source. Publish the source or remove that reference first.'],
    [429, 'rate_limit', 'Too many requests. Wait a moment, then retry.'],
    [502, 'invalid_response', 'The server returned incomplete data. Please retry.'],
    [422, 'unprocessable_entity', 'This selection could not be prepared. Check your learning settings or choose a smaller scope.'],
    [500, 'internal_error', 'Could not load this information. Check your connection and retry.'],
    [503, 'service_unavailable', 'Could not load this information. Check your connection and retry.'],
  ]

  test.each(cases)(
    'maps status=%i code=%s to expected message',
    (status, code, expectedMessage) => {
      expect(resolveApiErrorMessage(status, code)).toBe(expectedMessage)
      const error = new ApiError(status, code)
      expect(error.message).toBe(expectedMessage)
    },
  )

  test('ApiError preserves constructor metadata and optional fields', () => {
    const invalidParams = [{ name: 'handle', reason: 'too_short' }]
    const error = new ApiError(
      400,
      'invalid_handle',
      'The handle provided was too short',
      'req-12345',
      '/v1/users/me',
      invalidParams,
    )

    expect(error).toBeInstanceOf(Error)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(400)
    expect(error.code).toBe('invalid_handle')
    expect(error.detail).toBe('The handle provided was too short')
    expect(error.requestId).toBe('req-12345')
    expect(error.instance).toBe('/v1/users/me')
    expect(error.invalidParams).toEqual(invalidParams)
    expect(error.message).toBe('Use 3–30 lowercase letters, numbers or underscores, starting with a letter.')

    error.retryAfterSeconds = 60
    expect(error.retryAfterSeconds).toBe(60)
  })

  test('401 status takes precedence over specific domain error codes', () => {
    expect(resolveApiErrorMessage(401, 'quota_exceeded')).toBe('Your session has expired. Sign in again.')
    expect(resolveApiErrorMessage(401, 'node_not_found')).toBe('Your session has expired. Sign in again.')
  })

  test('429 status takes precedence over generic codes other than 401', () => {
    expect(resolveApiErrorMessage(429, 'custom_throttling')).toBe('Too many requests. Wait a moment, then retry.')
  })

  test('invalid_response code returns incomplete data message across non-401/429 statuses', () => {
    expect(resolveApiErrorMessage(502, 'invalid_response')).toBe('The server returned incomplete data. Please retry.')
    expect(resolveApiErrorMessage(500, 'invalid_response')).toBe('The server returned incomplete data. Please retry.')
  })

  test('422 status provides custom guidance when code is unmapped', () => {
    expect(resolveApiErrorMessage(422, 'unknown_validation_code')).toBe(
      'This selection could not be prepared. Check your learning settings or choose a smaller scope.',
    )
  })
})
