/**
 * The folder / deck / reference tree, and the analytics hung off it.
 *
 * Derived from `reports/v1-openapi-snapshot.json`.
 */

export type NodeType = "FOLDER" | "DECK" | "REFERENCE"

/**
 * Only two values. The previously hand-written type also listed `UNLISTED`,
 * which the API has never served: a public item is reachable by direct link and
 * is absent from listings, so "unlisted" is what `PUBLIC` already means here.
 */
export type Visibility = "PRIVATE" | "PUBLIC"

/** One step in a node's ancestor chain, for breadcrumbs. */
export interface NodeAncestor {
  id: string
  name: string
  type: NodeType
}

export interface NodeRead {
  id: string
  type: NodeType
  name: string
  visibility: Visibility
  description?: string | null
  parentNodeId?: string | null
  /** Set only on a REFERENCE, which points at a deck elsewhere in the tree. */
  targetNodeId?: string | null
  /** Root-first ancestor chain. Absent on list reads, present on a single read. */
  path?: NodeAncestor[] | null
  /** Deck size. Absent where the API did not compute it, not zero. */
  itemCount?: number | null
  createdAt?: string | null
  updatedAt?: string | null
}

export interface NodePage {
  items: NodeRead[]
  /** Null on the last page. */
  nextCursor?: string | null
}

export interface NodeCreate {
  type: NodeType
  name: string
  parentNodeId?: string | null
  targetNodeId?: string | null
  description?: string | null
  visibility?: Visibility
  /**
   * Publishing a folder publishes everything beneath it, so the API refuses
   * without this and returns `folder_publication_requires_confirmation`.
   */
  confirmSubtreePublication?: boolean
}

export interface NodeUpdate {
  name?: string | null
  description?: string | null
}

export interface NodeMove {
  /** Null moves the node to the root. */
  parentNodeId?: string | null
}

export interface NodeVisibilityUpdate {
  visibility: Visibility
  confirmSubtreePublication?: boolean
}

// Session-shape settings live in `learning.ts`. They belong to the learner rather
// than to a deck, so they are served from `/v1/me/learning-settings` and have
// nothing to do with the node tree.

// Folder analytics DTOs live in `analytics.ts`. The same shapes are served by
// both the folder-scoped and the global endpoints, so defining them here as well
// would be two declarations of one wire contract.
