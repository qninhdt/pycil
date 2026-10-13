import { getApiBaseUrl } from './services/config'
import { ApiError } from './error'

export async function apiRequest<T>(path: string, token: string | null, parse: (value: unknown) => T, signal: AbortSignal, body?: unknown, method?: 'POST' | 'PATCH' | 'DELETE', extraHeaders?: Record<string, string>): Promise<T> {
  const url = `${getApiBaseUrl()}/${path.replace(/^\//, '')}`
  const response = await fetch(url, {
    method: method ?? (body === undefined ? 'GET' : 'POST'), cache: 'no-store', signal,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const value: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new ApiError(response.status, value && typeof value === 'object' && 'error' in value && typeof value.error === 'string' ? value.error : 'request_failed')
  return parse(value)
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
