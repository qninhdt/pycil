import "server-only"

import { isRefreshExpired } from "@/lib/auth/session-validity"
import type { SessionData } from "@/lib/auth/types"

import { ApiError, type ApiErrorEnvelope } from "./errors"
import type { AuthTokens } from "./types"
import { apiUrl } from "./upstream"

/**
 * The one place a request leaves for the API.
 *
 * Server-only by construction: the bearer token lives in the sealed session
 * cookie and `PYCIL_API_URL` is an unprefixed environment variable, so neither
 * can be read from a browser bundle. Every resource module in `./resources`
 * closes over a fetcher built here rather than calling `fetch` itself.
 *
 * No case transform is applied. The API serialises every response by alias, so
 * bodies arrive camelCase already; a blanket transform would also rewrite the
 * question payload keys the dictionary supplies verbatim.
 */

/** Refresh this far ahead of expiry, so an in-flight request cannot straddle it. */
const REFRESH_WINDOW_SECONDS = 60

// Several server-side reads can share one session object. Refresh-token rotation
// makes those refreshes a single-flight operation: the second caller must await the
// first result instead of replaying the token that the first caller just consumed.
const pendingRefreshes = new WeakMap<SessionData, Promise<string | undefined>>()

// Separate server requests deserialize the same cookie into separate objects, so
// object identity cannot protect the refresh endpoint from a rotation race. This
// short-lived process-wide map coalesces those requests by the token they consume.
const pendingTokenRefreshes = new Map<string, Promise<AuthTokens | undefined>>()

export type Fetcher = <T>(path: string, options?: RequestInit) => Promise<T>

export interface FetcherOptions {
  /** Whether this caller can rotate and persist the sealed session cookie. */
  refresh?: boolean
}

/** A rotated session could not be written back to the sealed cookie. */
export class SessionPersistenceError extends Error {
  readonly code = "session_persistence_failed"

  constructor() {
    super("Could not persist the refreshed session after token rotation")
    this.name = "SessionPersistenceError"
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

/**
 * Returns a usable access token, refreshing it in place when it is about to
 * expire.
 *
 * A refresh rotates the pair on the server, so the old refresh token stops
 * working the moment the new one is issued. Writing the new values only onto the
 * in-memory object would leave the sealed cookie holding a token the API has
 * already invalidated: the session keeps presenting as signed in while every
 * request it makes comes back 401. So the session is re-sealed here.
 *
 * A caller that cannot write the cookie must not continue with a rotated token:
 * its next request would present the consumed refresh credential again. Plain
 * Server Component reads opt out before this function is reached.
 */
async function refreshAccessToken(
  session: SessionData,
  now: number
): Promise<string | undefined> {
  const refreshToken = session.refreshToken
  if (!refreshToken) return session.accessToken

  let tokens: AuthTokens | undefined
  try {
    tokens = await refreshTokens(refreshToken)
  } catch (error) {
    // A failed refresh is not a failed request. The current token may still have
    // seconds left on it, and the API will say so if it does not.
    console.warn(
      "Token refresh failed; continuing with the current token:",
      error
    )
    return session.accessToken
  }

  if (!tokens) return session.accessToken

  session.accessToken = tokens.accessToken
  session.refreshToken = tokens.refreshToken
  session.expiresAt = now + tokens.expiresIn
  session.refreshExpiresAt = now + tokens.refreshExpiresIn

  if (!(await persistSession(session))) {
    throw new SessionPersistenceError()
  }
  return session.accessToken
}

async function refreshTokens(refreshToken: string): Promise<AuthTokens | undefined> {
  const pending = pendingTokenRefreshes.get(refreshToken)
  if (pending) return pending

  const request = (async () => {
    const response = await fetch(`${apiUrl()}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // A request body, not a response: the refresh endpoint accepts
      // `refresh_token` and is not aliased. Sending `refreshToken` here fails
      // validation.
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    })

    if (!response.ok) return undefined
    return (await response.json()) as AuthTokens
  })()
  pendingTokenRefreshes.set(refreshToken, request)

  try {
    return await request
  } finally {
    if (pendingTokenRefreshes.get(refreshToken) === request) {
      pendingTokenRefreshes.delete(refreshToken)
    }
  }
}

async function ensureAccessToken(
  session: SessionData,
  allowRefresh = true,
): Promise<string | undefined> {
  if (!session.accessToken) return undefined

  const now = Math.floor(Date.now() / 1000)
  const expiresAt = session.expiresAt ?? 0

  if (!allowRefresh || expiresAt - now >= REFRESH_WINDOW_SECONDS || !session.refreshToken) {
    return session.accessToken
  }

  // An expired refresh token cannot produce anything. Asking anyway costs a round
  // trip to be told so, on every request, for as long as the cookie survives — and
  // the login gate reads the same field, so a learner in this state is on their way
  // to `/login` rather than waiting on this call.
  if (isRefreshExpired(session, now)) return session.accessToken

  const pending = pendingRefreshes.get(session)
  if (pending) return pending

  const refresh = refreshAccessToken(session, now)
  pendingRefreshes.set(session, refresh)
  try {
    return await refresh
  } finally {
    if (pendingRefreshes.get(session) === refresh)
      pendingRefreshes.delete(session)
  }
}

/** Return the token for a raw server-side request, sharing refresh semantics. */
export async function accessTokenForRequest(
  session: SessionData,
  options: FetcherOptions = { refresh: true },
): Promise<string | undefined> {
  return ensureAccessToken(session, options.refresh ?? true)
}

/**
 * Re-seal the session cookie and report whether persistence was possible.
 *
 * `getSession` returns an iron-session object carrying `save`, but the shared
 * `SessionData` shape describes only the payload — the callback route is the one
 * place that names the method today. Rather than widen the payload type, the
 * capability is probed for, which also covers plain-object sessions in tests.
 */
async function persistSession(session: SessionData): Promise<boolean> {
  const save = (session as SessionData & { save?: () => Promise<void> }).save
  // Plain objects are useful in unit tests and do not represent a cookie that can
  // become stale, so there is nothing to persist at this seam.
  if (typeof save !== "function") return true

  try {
    await save.call(session)
    return true
  } catch (error) {
    // A caller that cannot write the cookie must not continue with a rotated token:
    // its next request would present the consumed refresh credential again.
    console.debug(
      "Could not persist the refreshed session in this context:",
      error
    )
    return false
  }
}

export function createFetcher(
  session: SessionData,
  options: FetcherOptions = { refresh: true },
): Fetcher {
  return async function apiFetch<T>(
    path: string,
    requestOptions: RequestInit = {}
  ): Promise<T> {
    const token = await ensureAccessToken(session, options.refresh ?? true)
    const headers = new Headers(requestOptions.headers)

    if (token) headers.set("Authorization", `Bearer ${token}`)
    if (typeof requestOptions.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json")
    }

    const response = await fetch(`${apiUrl()}${path}`, {
      ...requestOptions,
      headers,
      cache: "no-store",
    })

    if (response.status === 204) return undefined as T

    let body: unknown
    try {
      body = await response.json()
    } catch {
      body = null
    }

    if (!response.ok) {
      if (isObject(body) && "error" in body) {
        const envelope = body as unknown as ApiErrorEnvelope
        throw new ApiError(
          envelope.error.code,
          envelope.error.message,
          response.status,
          envelope.error.requestId,
          envelope.error.details
        )
      }
      // No envelope means the failure did not come from the application: a proxy,
      // a gateway, or a crash before the handler ran.
      throw new ApiError(
        "http_error",
        `API request failed with status ${response.status}`,
        response.status
      )
    }

    return body as T
  }
}

/** Builds a `?a=b` suffix, omitting the `?` when nothing was set. */
export function queryString(
  params: Record<string, string | number | undefined | null>
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value))
    }
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}
