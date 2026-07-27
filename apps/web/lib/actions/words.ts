"use server"

import { createApiClient } from "@/lib/api/client"
import { handleAction, type ActionResult } from "@/lib/api/handle-api-error"
import type {
  GenerationCreateRead,
  SenseAddResponse,
  WordSearchRead,
} from "@/lib/api/types"
import { getSession } from "@/lib/auth/session"

/**
 * The palette's three server actions.
 *
 * They exist as actions rather than as route handlers because each one is called
 * from a client component with no need for a URL of its own, and the session
 * cookie is read on the server either way: the bearer token never reaches the
 * browser.
 */

const SIGNED_OUT = {
  success: false as const,
  error: "Sign in to continue",
  code: "not_authenticated",
}

export async function searchWords(
  query: string,
): Promise<ActionResult<WordSearchRead[]>> {
  const trimmed = query.trim()
  // An empty query is not an error and not a request: the API would reject it and
  // the palette would show a failure for having typed nothing.
  if (trimmed.length === 0) return { success: true, data: [] }

  const session = await getSession()
  if (!session.isLoggedIn) return SIGNED_OUT

  const client = createApiClient(session)
  return handleAction(() => client.searchWords(trimmed))
}

/**
 * Starts a word generation and returns its task id. The work itself is
 * asynchronous; the caller registers the id with the activity store so the
 * result is still reachable after a reload.
 */
export async function generateWord(
  query: string,
): Promise<ActionResult<GenerationCreateRead>> {
  const trimmed = query.trim()
  if (trimmed.length === 0) {
    return { success: false, error: "Type a word first", code: "empty_query" }
  }

  const session = await getSession()
  if (!session.isLoggedIn) return SIGNED_OUT

  const client = createApiClient(session)
  return handleAction(() => client.submitWordGeneration(trimmed))
}

/**
 * Adds a sense to a deck.
 *
 * This is the mutation that bumps the deck's structural generation, along with
 * every ancestor and reverse reference of it, which is why the palette confirms
 * first when a session is live.
 */
export async function addSenseToDeck(
  nodeId: string,
  senseId: number,
): Promise<ActionResult<SenseAddResponse>> {
  const session = await getSession()
  if (!session.isLoggedIn) return SIGNED_OUT

  const client = createApiClient(session)
  return handleAction(() => client.addSenseToDeck(nodeId, senseId))
}
