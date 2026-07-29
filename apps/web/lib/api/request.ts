import "server-only"

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
 * The refreshed values are written back onto the session object the caller
 * passed in. Persisting them is the caller's business: a read during render
 * cannot save a cookie, so the new token is used for this request and sealed
 * only when a route handler or action saves the session.
 */
async function ensureAccessToken(session: SessionData): Promise<string | undefined> {
  if (!session.accessToken) return undefined

  const now = Math.floor(Date.now() / 1000)
  const expiresAt = session.expiresAt ?? 0

  if (expiresAt - now >= REFRESH_WINDOW_SECONDS || !session.refreshToken) {
    return session.accessToken
  }

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
  } catch (error) {
    // A failed refresh is not a failed request. The current token may still have
    // seconds left on it, and the API will say so if it does not.
    console.warn("Token refresh failed; continuing with the current token:", error)
  }

  return session.accessToken
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
