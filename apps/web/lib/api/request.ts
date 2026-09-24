import { ApiError } from "./errors"

export type Fetcher = <T>(path: string, options?: RequestInit) => Promise<T>

function apiOrigin(): string {
  return process.env.NEXT_PUBLIC_API_URL ? process.env.NEXT_PUBLIC_API_URL.replace(/\/v1\/?$/, "") : ""
}

function requestId(): string {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}`
}

async function headersFor(options: RequestInit = {}): Promise<Headers> {
  const headers = new Headers(options.headers)
  headers.set("X-Request-ID", headers.get("X-Request-ID") ?? requestId())
  if (typeof options.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }
  if (!headers.has("Authorization") && typeof window !== "undefined") {
    try {
      const clerkToken = await (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string | null> } } })
        ?.Clerk?.session?.getToken()
      if (clerkToken) {
        headers.set("Authorization", `Bearer ${clerkToken}`)
      }
    } catch {
      // Ignore if session not active
    }
  }
  return headers
}

async function parseError(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // Non-JSON response
  }
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const problem = body as {
      code?: unknown
      detail?: unknown
      requestId?: unknown
      details?: unknown
    }
    if (typeof problem.code === "string" && typeof problem.detail === "string") {
      return new ApiError(
        problem.code,
        problem.detail,
        response.status,
        typeof problem.requestId === "string" ? problem.requestId : undefined,
        problem.details && typeof problem.details === "object"
          ? (problem.details as Record<string, unknown>)
          : undefined,
      )
    }
  }
  return new ApiError(
    "http_error",
    `API request failed with status ${response.status}`,
    response.status,
    response.headers.get("X-Request-ID") ?? undefined,
  )
}

export function createFetcher(): Fetcher {
  return async function apiFetch<T>(
    path: string,
    requestOptions: RequestInit = {},
  ): Promise<T> {
    const method = (requestOptions.method ?? "GET").toUpperCase()
    const headers = await headersFor(requestOptions)

    const response = await fetch(`${apiOrigin()}${path}`, {
      ...requestOptions,
      method,
      headers,
      credentials: "include",
      cache: "no-store",
    })

    if (!response.ok) throw await parseError(response)
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }
}

export async function fetchStream(path: string, options: RequestInit = {}): Promise<Response> {
  const headers = await headersFor(options)
  return await fetch(`${apiOrigin()}${path}`, {
    ...options,
    headers,
    credentials: "include",
    cache: "no-store",
  })
}

export function queryString(
  params: Record<string, string | number | undefined | null>,
): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value))
  }
  const encoded = search.toString()
  return encoded ? `?${encoded}` : ""
}
