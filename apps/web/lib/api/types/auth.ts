/**
 * Identity, capabilities and the two token shapes.
 *
 * Derived from `reports/v1-openapi-snapshot.json`, not transcribed from the
 * Python models. Where the document and a hand-written type disagreed, the
 * document won — that is the whole point of archiving it.
 */

/**
 * What `GET /v1/me` returns.
 *
 * Deliberately no `tokenVersion`. It is the auth revocation counter, checked
 * server-side when authorising a realtime subscribe, and the API stopped
 * serving it here. A client has no use for it and no business holding it.
 */
export interface Viewer {
  id: string
  email: string
  name?: string | null
  image?: string | null
}

export interface Capabilities {
  assistant: boolean
  /** Absent on older builds; the API defaults it to true. */
  realtime?: boolean
}

/** `GET /v1/auth/callback` and `POST /v1/auth/refresh`. Server-side only. */
export interface AuthTokens {
  accessToken: string
  refreshToken: string
  tokenType: string
  expiresIn: number
  refreshExpiresIn: number
}

export interface LoginStart {
  authorizeUrl: string
}

/**
 * `GET /v1/realtime/token`. Distinct from `AuthTokens`: this one is scoped to a
 * Centrifugo connection and is short-lived, which is why the provider re-mints
 * rather than holding its first value.
 */
export interface RealtimeToken {
  token: string
  /** Unix seconds. The subscribe proxy denies anything past it. */
  expiresAt: number
  sseUrl: string
}

/** `GET /v1/me/export`. Each section is an opaque snapshot, not a typed model. */
export interface AccountExport {
  profile: Record<string, unknown>
  hierarchy: Record<string, unknown>[]
  learning: Record<string, unknown>
  assistant: Record<string, unknown>
  wordGenerations: Record<string, unknown>[]
}
