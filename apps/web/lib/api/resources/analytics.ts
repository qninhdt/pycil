import type { Fetcher } from "../request"
import { queryString } from "../request"
import type {
  CefrDistribution,
  DashboardStats,
  FolderItem,
  FolderStats,
  HistoryBucket,
  WeakSense,
} from "../types"

/**
 * Analytics, at two scopes.
 *
 * Every read is served by one route under `/v1/me/*` with an optional `nodeId`
 * query parameter: present means "that folder's readable subtree", absent means
 * "everything the learner tracks". The responses are identical at both scopes, so
 * the folder and global readers share their return types and differ only in that
 * parameter.
 *
 * This is deliberate on the server rather than a folder-scoped path per read. A
 * sense held in two decks must be counted once, and one route with one scope
 * predicate is what guarantees that — the account scope is not a client-side
 * fan-out over roots. It also means there is no `/v1/folders/{id}/stats`; the
 * folder scope of a stat is a parameter, not a path.
 */
export function analyticsResource(fetch: Fetcher) {
  return {
    getDashboard: () => fetch<DashboardStats>("/v1/learning/dashboard"),

    /**
     * The senses beneath a folder, flattened across its whole subtree.
     *
     * The one read that genuinely has its own path: it returns a page of senses
     * rather than an aggregate, so it is not a scoped variant of a `/me/*` read.
     *
     * Paged by offset because the API caps `limit` at 200: a folder above a dozen
     * decks can hold more senses than one response should carry.
     */
    getFolderItems: (nodeId: string, offset = 0, limit = 50) =>
      fetch<FolderItem[]>(`/v1/folders/${nodeId}/items${queryString({ offset, limit })}`),

    getFolderStats: (nodeId: string) =>
      fetch<FolderStats>(`/v1/me/stats${queryString({ nodeId })}`),

    getFolderWeakest: (nodeId: string, limit = 10) =>
      fetch<WeakSense[]>(`/v1/me/weakest${queryString({ nodeId, limit })}`),

    getFolderCefr: (nodeId: string) =>
      fetch<CefrDistribution>(`/v1/me/cefr${queryString({ nodeId })}`),

    getFolderHistory: (nodeId: string, from?: string, to?: string) =>
      fetch<HistoryBucket[]>(`/v1/me/history${queryString({ nodeId, from, to })}`),

    getGlobalStats: () => fetch<FolderStats>("/v1/me/stats"),

    getGlobalWeakest: (limit = 10) =>
      fetch<WeakSense[]>(`/v1/me/weakest${queryString({ limit })}`),

    getGlobalCefr: () => fetch<CefrDistribution>("/v1/me/cefr"),

    /**
     * Review history in buckets. An inverted or over-long window is rejected with
     * `history_window_invalid` rather than silently clamped.
     */
    getGlobalHistory: (from?: string, to?: string) =>
      fetch<HistoryBucket[]>(`/v1/me/history${queryString({ from, to })}`),
  }
}
