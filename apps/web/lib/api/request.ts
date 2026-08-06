import "server-only"

import { isRefreshExpired } from "@/lib/auth/session-validity"
import type { SessionData } from "@/lib/auth/types"

import { ApiError, type ApiErrorEnvelope } from "./errors"
import type { AuthTokens } from "./types"

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

export type Fetcher = <T>(path: string, options?: RequestInit) => Promise<T>

function apiBaseUrl(): string {
  return process.env.PYCIL_API_URL || "http://localhost:8000"
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
 * Sealing can legitimately fail. A cookie cannot be written while a server
 * component renders, and Next.js throws if you try. That is not an error worth
 * failing the request over — the fresh token is already in hand and serves this
 * request; the next mutating action or route handler will seal it. So a failed
 * save is swallowed, and only a genuinely unexpected one is surfaced in logs.
 */
async function ensureAccessToken(session: SessionData): Promise<string | undefined> {
  if (!session.accessToken) return undefined

  const now = Math.floor(Date.now() / 1000)
  const expiresAt = session.expiresAt ?? 0

  if (expiresAt - now >= REFRESH_WINDOW_SECONDS || !session.refreshToken) {
    return session.accessToken
  }

  // An expired refresh token cannot produce anything. Asking anyway costs a round
  // trip to be told so, on every request, for as long as the cookie survives — and
  // the login gate reads the same field, so a learner in this state is on their way
  // to `/login` rather than waiting on this call.
  if (isRefreshExpired(session, now)) return session.accessToken

  try {
    const response = await fetch(`${apiBaseUrl()}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // A request body, not a response: the refresh endpoint accepts
      // `refresh_token` and is not aliased. Sending `refreshToken` here fails
      // validation.
      body: JSON.stringify({ refresh_token: session.refreshToken }),
      cache: "no-store",
    })

    if (!response.ok) return session.accessToken

    const tokens = (await response.json()) as AuthTokens
    session.accessToken = tokens.accessToken
    session.refreshToken = tokens.refreshToken
    session.expiresAt = now + tokens.expiresIn
    session.refreshExpiresAt = now + tokens.refreshExpiresIn

    await persistSession(session)
  } catch (error) {
    // A failed refresh is not a failed request. The current token may still have
    // seconds left on it, and the API will say so if it does not.
    console.warn("Token refresh failed; continuing with the current token:", error)
  }

  return session.accessToken
}

/**
 * Re-seal the session cookie, tolerating the render-context refusal.
 *
 * `getSession` returns an iron-session object carrying `save`, but the shared
 * `SessionData` shape describes only the payload — the callback route is the one
 * place that names the method today. Rather than widen the payload type, the
 * capability is probed for, which also covers plain-object sessions in tests.
 */
async function persistSession(session: SessionData): Promise<void> {
  const save = (session as SessionData & { save?: () => Promise<void> }).save
  if (typeof save !== "function") return

  try {
    await save.call(session)
  } catch (error) {
    // Expected during render: "Cookies can only be modified in a Server Action
    // or Route Handler". The token still serves this request.
    console.debug("Could not persist the refreshed session in this context:", error)
  }
}

export function createFetcher(session: SessionData): Fetcher {
  return async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await ensureAccessToken(session)
    const headers = new Headers(options.headers)

    if (token) headers.set("Authorization", `Bearer ${token}`)
    if (typeof options.body === "string" && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json")
    }

    const response = await fetch(`${apiBaseUrl()}${path}`, {
      ...options,
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
          envelope.error.details,
        )
      }
      // No envelope means the failure did not come from the application: a proxy,
      // a gateway, or a crash before the handler ran.
      throw new ApiError(
        "http_error",
        `API request failed with status ${response.status}`,
        response.status,
      )
    }

    return body as T
  }
}

/** Builds a `?a=b` suffix, omitting the `?` when nothing was set. */
export function queryString(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, String(value))
    }
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}
