import type { Fetcher } from "../request"
import { queryString } from "../request"
import type {
  NodeCreate,
  NodeMove,
  NodePage,
  NodeRead,
  NodeUpdate,
  NodeVisibilityUpdate,
  SenseAdded,
  SenseContent,
} from "../types"

/** The folder / deck / reference tree, and a deck's contents. */
export function hierarchyResource(fetch: Fetcher) {
  return {
    /** One level of the tree. `parentNodeId` omitted lists the roots. */
    listNodes: (parentNodeId?: string | null, cursor?: string, limit = 50) =>
      fetch<NodePage>(
        `/v1/nodes${queryString({ parentNodeId, cursor, limit })}`,
      ),

    /** A single node, with its root-first ancestor chain for breadcrumbs. */
    getNode: (nodeId: string) => fetch<NodeRead>(`/v1/nodes/${nodeId}`),

    createNode: (data: NodeCreate) =>
      fetch<NodeRead>("/v1/nodes", {
        method: "POST",
        body: JSON.stringify(data),
      }),

    updateNode: (nodeId: string, data: NodeUpdate) =>
      fetch<NodeRead>(`/v1/nodes/${nodeId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    /** Null `parentNodeId` moves the node to the root. */
    moveNode: (nodeId: string, data: NodeMove) =>
      fetch<NodeRead>(`/v1/nodes/${nodeId}/move`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    /**
     * Publishing a folder publishes its whole subtree, so the API refuses
     * without `confirmSubtreePublication` and answers
     * `folder_publication_requires_confirmation`.
     */
    updateNodeVisibility: (nodeId: string, data: NodeVisibilityUpdate) =>
      fetch<NodeRead>(`/v1/nodes/${nodeId}/visibility`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),

    deleteNode: (nodeId: string) =>
      fetch<void>(`/v1/nodes/${nodeId}`, { method: "DELETE" }),

    getDeckItems: (nodeId: string) =>
      fetch<SenseContent[]>(`/v1/decks/${nodeId}/items`),

    /**
     * Adds a sense to a deck.
     *
     * This bumps the deck's structural generation and propagates to every
     * ancestor and reverse reference, which can invalidate a live session
     * scoped to a parent folder.
     */
    addSenseToDeck: (nodeId: string, senseId: number) =>
      fetch<SenseAdded>(`/v1/decks/${nodeId}/senses`, {
        method: "POST",
        body: JSON.stringify({ senseId }),
      }),

    removeSenseFromDeck: (nodeId: string, senseId: number) =>
      fetch<void>(`/v1/decks/${nodeId}/senses/${senseId}`, { method: "DELETE" }),
  }
}
