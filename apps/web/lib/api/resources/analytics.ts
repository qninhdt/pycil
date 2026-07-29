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
 * Each shape is served both for one folder subtree and across everything the
 * learner tracks. The responses are identical, so the folder and global readers
 * share their return types and differ only in path.
 */
export function analyticsResource(fetch: Fetcher) {
  return {
    getDashboard: () => fetch<DashboardStats>("/v1/learning/dashboard"),

    getFolderStats: (nodeId: string) => fetch<FolderStats>(`/v1/folders/${nodeId}/stats`),

    /**
     * The senses beneath a folder, flattened across its whole subtree.
     *
     * Paged by offset because the API caps `limit` at 200: a folder above a dozen
     * decks can hold more senses than one response should carry.
     */
    getFolderItems: (nodeId: string, offset = 0, limit = 50) =>
      fetch<FolderItem[]>(`/v1/folders/${nodeId}/items${queryString({ offset, limit })}`),

    getFolderWeakest: (nodeId: string, limit = 10) =>
      fetch<WeakSense[]>(`/v1/folders/${nodeId}/weakest${queryString({ limit })}`),

    getFolderCefr: (nodeId: string) => fetch<CefrDistribution>(`/v1/folders/${nodeId}/cefr`),

    getFolderHistory: (nodeId: string, from?: string, to?: string) =>
      fetch<HistoryBucket[]>(`/v1/folders/${nodeId}/history${queryString({ from, to })}`),

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
