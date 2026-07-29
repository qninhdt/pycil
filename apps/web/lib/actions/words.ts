"use server"

import { revalidatePath } from "next/cache"

import type { ActionResult } from "@/lib/api/handle-api-error"
import type { GenerationCreated, SenseAdded, WordSearchResult } from "@/lib/api/types"

import { withClient } from "./authorized-action"

/**
 * The palette's three actions.
 *
 * They are actions rather than route handlers because each is called from a
 * client component with no need for a URL of its own, and the session cookie is
 * read on the server either way: the bearer token never reaches the browser.
 */

export async function searchWords(
  query: string,
): Promise<ActionResult<WordSearchResult[]>> {
  const trimmed = query.trim()
  // An empty query is not an error and not a request. Sending it would fail
  // validation and the palette would report a failure for having typed nothing.
  if (trimmed.length === 0) return { success: true, data: [] }

  return withClient((client) => client.content.searchWords(trimmed))
}

/**
 * Starts a word generation and returns its task id.
 *
 * The work itself is asynchronous. The caller registers the id with the activity
 * store, which is what keeps the result reachable after a reload.
 */
export async function generateWord(
  query: string,
): Promise<ActionResult<GenerationCreated>> {
  const trimmed = query.trim()
  if (trimmed.length === 0) {
    return { success: false, error: "Type a word first.", code: "empty_query" }
  }

  return withClient((client) => client.content.generateWord(trimmed))
}

/**
 * Adds a sense to a deck.
 *
 * This bumps the deck's structural generation and propagates to every ancestor
 * and reverse reference, which is why the palette confirms first when a session
 * is live: the addition can invalidate a session scoped to a parent folder.
 *
 * The deck page is revalidated so the new word is present on the next visit
 * rather than after a manual refresh.
 */
export async function addSenseToDeck(
  nodeId: string,
  senseId: number,
): Promise<ActionResult<SenseAdded>> {
  const result = await withClient((client) =>
    client.hierarchy.addSenseToDeck(nodeId, senseId),
  )
  if (result.success) revalidatePath(`/library/${nodeId}`)
  return result
}
