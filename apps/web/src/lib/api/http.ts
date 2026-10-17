import { getApiBaseUrl } from './services/config'
import { ApiError, type ProblemDetailsPayload } from './error'

export async function apiRequest<T>(path: string, token: string | null, parse: (value: unknown, response?: Response) => T, signal: AbortSignal, body?: unknown, method?: 'POST' | 'PATCH' | 'DELETE', extraHeaders?: Record<string, string>): Promise<T> {
  const url = `${getApiBaseUrl()}/${path.replace(/^\//, '')}`
  const response = await fetch(url, {
    method: method ?? (body === undefined ? 'GET' : 'POST'), cache: 'no-store', signal,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const value: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const payload = (value && typeof value === 'object' ? value : null) as ProblemDetailsPayload | null
    const code =
      payload && typeof payload.code === 'string'
        ? payload.code
        : payload && typeof payload.error === 'string'
          ? payload.error
          : 'request_failed'
    const requestId =
      response.headers.get('x-request-id') ??
      (payload && typeof payload.request_id === 'string' ? payload.request_id : undefined)
    const detail = payload && typeof payload.detail === 'string' ? payload.detail : undefined
    const instance = payload && typeof payload.instance === 'string' ? payload.instance : undefined
    const invalidParams = payload && Array.isArray(payload.invalid_params) ? payload.invalid_params : undefined
    const error = new ApiError(response.status, code, detail, requestId, instance, invalidParams)
    const retry = Number(response.headers.get('Retry-After'))
    if (Number.isFinite(retry) && retry > 0) error.retryAfterSeconds = retry
    throw error
  }
  return parse(value, response)
}

export async function apiToken(getToken: () => Promise<string | null>, signal: AbortSignal): Promise<string> {
  let abort: () => void = () => {}
  try {
    const token = await Promise.race([getToken(), new Promise<never>((_, reject) => {
      abort = () => reject(signal.reason ?? new Error('Request cancelled.'))
      if (signal.aborted) abort()
      else signal.addEventListener('abort', abort, { once: true })
    })])
    if (!token) throw new ApiError(401, 'authentication_required')
    return token
  } finally { signal.removeEventListener('abort', abort) }
}
