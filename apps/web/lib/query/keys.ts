/**
 * Every query key in the app, in one place.
 *
 * Keys are built from arguments rather than written as literals at call sites, so
 * a fetch and the invalidation that should clear it cannot drift apart. A typo in
 * a literal key is silent: the fetch works, the invalidation misses, and the
 * screen shows stale data with nothing to debug.
 *
 * Two things are deliberately absent:
 *
 * - `/v1/sessions/{id}/next` has **no key**. It mutates session state, so caching
 *   or refetching it destroys questions. See `resources/learning.ts`.
 * - Realtime task snapshots have no key either. They arrive over a subscription
 *   and live in the activity store, not in the query cache.
 */

/** Read as "everything under this domain" when passed to an invalidation. */
export const queryKeys = {
  viewer: () => ["viewer"] as const,

  capabilities: () => ["capabilities"] as const,

  nodes: {
    all: () => ["nodes"] as const,
    /** One level of the tree. `null` parent is the root listing, and is its own key. */
    list: (parentNodeId: string | null) => ["nodes", "list", parentNodeId] as const,
    detail: (nodeId: string) => ["nodes", "detail", nodeId] as const,
  },

  decks: {
    all: () => ["decks"] as const,
    items: (nodeId: string) => ["decks", nodeId, "items"] as const,
    settings: (nodeId: string) => ["decks", nodeId, "settings"] as const,
  },

  senses: {
    all: () => ["senses"] as const,
    detail: (senseId: number) => ["senses", senseId] as const,
  },

  words: {
    /** Search results are keyed by the exact query they answer. */
    search: (query: string) => ["words", "search", query] as const,
  },

  sessions: {
    /** The session's own state. Safe to cache: unlike `/next`, this only reads. */
    detail: (sessionId: string) => ["sessions", sessionId] as const,
  },

  analytics: {
    all: () => ["analytics"] as const,
    dashboard: () => ["analytics", "dashboard"] as const,
    /**
     * Folder-scoped and global analytics share response shapes but not keys: a
     * node id of `null` means "everything the learner tracks", which is a
     * different answer from any one subtree.
     */
    stats: (nodeId: string | null) => ["analytics", "stats", nodeId] as const,
    weakest: (nodeId: string | null, limit: number) =>
      ["analytics", "weakest", nodeId, limit] as const,
    cefr: (nodeId: string | null) => ["analytics", "cefr", nodeId] as const,
    history: (nodeId: string | null, from?: string, to?: string) =>
      ["analytics", "history", nodeId, from ?? null, to ?? null] as const,
    folderItems: (nodeId: string, offset: number, limit: number) =>
      ["analytics", "folderItems", nodeId, offset, limit] as const,
  },

  assistant: {
    all: () => ["assistant"] as const,
    threads: () => ["assistant", "threads"] as const,
    messages: (threadId: string) => ["assistant", "threads", threadId, "messages"] as const,
    run: (threadId: string, runId: string) =>
      ["assistant", "threads", threadId, "runs", runId] as const,
  },
} as const
