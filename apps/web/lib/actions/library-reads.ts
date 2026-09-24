import { createApiClient } from "@/lib/api/client"
import { ApiError } from "@/lib/api/errors"
import type {
  FolderItem,
  FolderStats,
  NodePage,
  NodeRead,
  SenseContent,
  SenseDetail,
} from "@/lib/api/types"

/**
 * Direct API reads used by the library and sense routes.
 *
 * Nothing here mutates, so there is no proxy endpoint to maintain.
 *
 * Every one of them works without a session. The API authorises node, deck item,
 * folder and sense reads with an optional caller, so a public item is readable by
 * someone with the link and no account. That is why these build a client from
 * whatever session exists instead of refusing when there is none.
 */

/** Null when the node is absent, private to someone else, or soft-deleted. */
export async function readNode(nodeId: string): Promise<NodeRead | null> {
  const client = createApiClient()
  return notFoundToNull(() => client.hierarchy.getNode(nodeId))
}

/** One level of the tree. Requires a caller: the API has no anonymous listing. */
export async function readNodeChildren(
  parentNodeId: string | null,
): Promise<NodePage> {
  try {
    return await createApiClient().hierarchy.listNodes(parentNodeId)
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return { items: [], nextCursor: null }
    }
    throw error
  }
}

/**
 * Whether this viewer may modify the node.
 *
 * `NodeRead` carries no owner field, so ownership cannot be read off the response.
 * A listing is owner-scoped (`author_id` is filtered server-side), but `getNode`
 * also serves someone else's public node — so a deep-linked node arrives with no
 * ownership signal at all.
 *
 * This asks the API instead of inferring: listing a node's children requires write
 * access on that node, so a 200 means owner and a 403 means read-only. It works for
 * all three kinds, since a deck or reference simply has no children to return.
 *
 * The alternative — showing edit controls and letting the mutation fail — puts a
 * rename dialog in front of someone who cannot rename anything.
 */
export async function canEditNode(nodeId: string): Promise<boolean> {
  const client = createApiClient()
  try {
    await client.hierarchy.listNodes(nodeId)
    return true
  } catch (error) {
    if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
      return false
    }
    throw error
  }
}

export async function readDeckItems(nodeId: string): Promise<SenseContent[]> {
  const client = createApiClient()
  return (await notFoundToNull(() => client.hierarchy.getDeckItems(nodeId))) ?? []
}

export interface FolderContents {
  stats: FolderStats | null
  items: FolderItem[]
  children: NodePage
}

/**
 * A folder's aggregate figures, its definitional item list, and its children.
 *
 * The three reads overlap rather than queue. Stats and items are allowed to come
 * back empty: the folder itself is already known to be readable, and a missing
 * aggregate is a reason to omit a figure, not to fail the page.
 */
export async function readFolderContents(nodeId: string): Promise<FolderContents> {
  const client = createApiClient()

  const [stats, items, children] = await Promise.all([
    notFoundToNull(() => client.analytics.getFolderStats(nodeId)),
    notFoundToNull(() => client.analytics.getFolderItems(nodeId)),
    readNodeChildren(nodeId),
  ])

  return { stats, items: items ?? [], children }
}

/** Null when the sense is unknown, unreferenced, or in no readable deck. */
export async function readSenseDetail(senseId: number): Promise<SenseDetail | null> {
  const client = createApiClient()
  return notFoundToNull(() => client.content.getSense(senseId))
}

/**
 * Turns "not found" into null and lets everything else through.
 *
 * The API deliberately answers 404 for unknown, unreferenced and unreadable alike,
 * so that a caller cannot probe which items exist or who owns them. A route reading
 * null therefore renders one not-found page without knowing which of the three it
 * was — which is the point.
 *
 * A 500, a timeout, or a dead dependency still throws, because those are the
 * route's error boundary to state rather than an empty screen to render.
 */
async function notFoundToNull<T>(read: () => Promise<T>): Promise<T | null> {
  try {
    return await read()
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}
