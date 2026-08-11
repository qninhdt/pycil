import "server-only"

import type { SessionData } from "@/lib/auth/types"

import { createFetcher, type FetcherOptions } from "./request"
import { analyticsResource } from "./resources/analytics"
import { assistantResource } from "./resources/assistant"
import { authResource } from "./resources/auth"
import { contentResource } from "./resources/content"
import { hierarchyResource } from "./resources/hierarchy"
import { learningResource } from "./resources/learning"

/**
 * The typed API surface, composed from one resource module per domain.
 *
 * Each resource closes over the same fetcher, so a token refresh triggered by one
 * call is visible to the next. Server Component reads leave refresh disabled by
 * default because their cookie store cannot be written; server actions and route
 * handlers pass `{ refresh: true }`. Nothing here is importable from a client component:
 * `server-only` makes that a build error rather than a leaked bearer token.
 *
 * Grouped by domain rather than flattened, so a call site reads
 * `client.learning.getNextQuestion(...)` and the domain a method belongs to is not
 * a naming convention you have to trust.
 */
export function createApiClient(
  session: SessionData,
  options: FetcherOptions = { refresh: false },
) {
  const fetch = createFetcher(session, options)

  return {
    auth: authResource(fetch),
    hierarchy: hierarchyResource(fetch),
    content: contentResource(fetch),
    learning: learningResource(fetch),
    analytics: analyticsResource(fetch),
    assistant: assistantResource(fetch),
  }
}

export type ApiClient = ReturnType<typeof createApiClient>
