import "server-only"

import { createApiClient, type ApiClient } from "@/lib/api/client"
import { handleAction, type ActionResult } from "@/lib/api/handle-api-error"
import type { SessionData } from "@/lib/auth/types"
import { getSession } from "@/lib/auth/session"

/**
 * The preamble every mutating action shares: read the sealed session, refuse if
 * there is no viewer, build a client, and convert a thrown `ApiError` into a
 * returned result.
 *
 * Returning rather than throwing matters at this boundary. An exception crossing
 * a server action reaches the client as an opaque digest with the message
 * stripped in production, so the caller cannot tell a quota refusal from a dead
 * database. A discriminated result carries the code the UI branches on.
 */

/**
 * Refusal for a signed-out caller.
 *
 * The code is not one the API can send — no request was made. It is deliberately
 * distinct from the API's own `unauthorized` so a caller can tell "we never
 * asked" from "the API rejected us".
 */
const SIGNED_OUT = {
  success: false as const,
  error: "Sign in to continue.",
  code: "not_authenticated",
}

export async function withClient<T>(
  run: (client: ApiClient) => Promise<T>,
  existingSession?: SessionData,
): Promise<ActionResult<T>> {
  const session = existingSession ?? await getSession()
  if (!session.isLoggedIn) return SIGNED_OUT

  const client = createApiClient(session, { refresh: true })
  return handleAction(() => run(client))
}
