"use server"

import { revalidatePath } from "next/cache"

import type { ActionResult } from "@/lib/api/handle-api-error"
import type {
  NodeCreate,
  NodeRead,
  NodeUpdate,
  NodeVisibilityUpdate,
} from "@/lib/api/types"

import { withClient } from "./authorized-action"

/**
 * Tree mutations: create, rename, move, publish, delete, and deck settings.
 *
 * Every one of these changes what a library listing shows, so each revalidates
 * the paths whose rendered output it just made wrong. A move touches two places —
 * where the node left and where it arrived — and both are revalidated even though
 * the caller was only looking at one.
 */

export async function createNode(data: NodeCreate): Promise<ActionResult<NodeRead>> {
  const result = await withClient((client) => client.hierarchy.createNode(data))
  if (result.success) {
    revalidatePath("/library")
    if (data.parentNodeId) revalidatePath(`/library/${data.parentNodeId}`)
  }
  return result
}

export async function updateNode(
  nodeId: string,
  data: NodeUpdate,
): Promise<ActionResult<NodeRead>> {
  const result = await withClient((client) => client.hierarchy.updateNode(nodeId, data))
  if (result.success) {
    revalidatePath("/library")
    revalidatePath(`/library/${nodeId}`)
  }
  return result
}

/** `parentNodeId: null` moves the node to the root. */
export async function moveNode(
  nodeId: string,
  parentNodeId: string | null,
): Promise<ActionResult<NodeRead>> {
  const result = await withClient((client) =>
    client.hierarchy.moveNode(nodeId, { parentNodeId }),
  )
  if (result.success) {
    // The origin is not known here — the API does not report where the node came
    // from — so the listing root is revalidated as the one page guaranteed to show
    // a stale position either way.
    revalidatePath("/library")
    revalidatePath(`/library/${nodeId}`)
    if (parentNodeId) revalidatePath(`/library/${parentNodeId}`)
  }
  return result
}

/**
 * Changes visibility.
 *
 * Publishing a folder publishes its entire subtree, which the API refuses without
 * `confirmSubtreePublication`. The refusal arrives as
 * `folder_publication_requires_confirmation` and is a prompt, not a failure: the
 * caller confirms and repeats the call with the flag set.
 */
export async function updateNodeVisibility(
  nodeId: string,
  data: NodeVisibilityUpdate,
): Promise<ActionResult<NodeRead>> {
  const result = await withClient((client) =>
    client.hierarchy.updateNodeVisibility(nodeId, data),
  )
  if (result.success) {
    revalidatePath("/library")
    revalidatePath(`/library/${nodeId}`)
  }
  return result
}

export async function deleteNode(nodeId: string): Promise<ActionResult<void>> {
  const result = await withClient((client) => client.hierarchy.deleteNode(nodeId))
  if (result.success) revalidatePath("/library")
  return result
}

export async function removeSenseFromDeck(
  nodeId: string,
  senseId: number,
): Promise<ActionResult<void>> {
  const result = await withClient((client) =>
    client.hierarchy.removeSenseFromDeck(nodeId, senseId),
  )
  if (result.success) revalidatePath(`/library/${nodeId}`)
  return result
}

/**
 * The folders a node could be moved into.
 *
 * A read rather than a mutation, but it lives here because only the move dialog
 * wants it and it is called from a client component. One level at a time: the API
 * pages by parent, and loading the whole tree to fill a picker would fetch every
 * node the learner owns to show a handful of choices.
 *
 * Decks and references are filtered out. Only a folder can hold children, and the
 * API answers `parent_must_be_owned_folder` for anything else — so offering one
 * would be offering a choice that cannot succeed.
 */
export async function listMoveDestinations(
  parentNodeId: string | null,
): Promise<ActionResult<NodeRead[]>> {
  const result = await withClient((client) => client.hierarchy.listNodes(parentNodeId))
  if (!result.success) return result
  return {
    success: true,
    data: result.data.items.filter((node) => node.type === "FOLDER"),
  }
}
