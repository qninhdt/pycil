/**
 * Identity and capability flags. Credentials are HttpOnly cookies and have no
 * browser-readable TypeScript shape.
 *
 * Derived from `reports/v1-openapi-snapshot.json`, not transcribed from the
 * Python models. Where the document and a hand-written type disagreed, the
 * document won — that is the whole point of archiving it.
 */

/**
 * What `GET /v1/me` returns.
 *
 * Deliberately no `tokenVersion`. It is the auth revocation counter, checked
 * server-side when authorising a request, and the API stopped
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
}

/** `GET /v1/me/export`. Each section is an opaque snapshot, not a typed model. */
export interface AccountExport {
  profile: Record<string, unknown>
  hierarchy: Record<string, unknown>[]
  learning: Record<string, unknown>
  assistant: Record<string, unknown>
}
