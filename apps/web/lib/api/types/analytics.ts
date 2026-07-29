/**
 * Dashboard figures and the folder-or-global analytics reads.
 *
 * Every shape here is served at two scopes: under `/v1/folders/{nodeId}/...` for
 * one subtree, and under `/v1/me/...` across everything the learner tracks. The
 * types are shared because the responses are identical; only the scope differs.
 */

export interface FolderStats {
  total: number
  learned: number
  mastered: number
  avgMastery: number
}

export interface FolderItem {
  senseId: number
  definition: string
  tier: string
  cefrLevel?: string | null
}

/**
 * A weakest-sense row, carrying enough to render without a second request.
 *
 * The content fields are nullable on purpose: a sense regenerated away upstream
 * still has local statistics, and the API keeps the row rather than dropping it.
 * A renderer therefore has to cope with a mastery score and no headword.
 */
export interface WeakSense {
  senseId: number
  mastery: number
  word?: string | null
  definition?: string | null
  pos?: string | null
  cefrLevel?: string | null
}

/** CEFR level to count. An open map: the levels present depend on the data. */
export type CefrDistribution = Record<string, number>

export interface HistoryBucket {
  bucket: string
  reviewed: number
  avgMastery: number
}

export interface ForecastDay {
  date: string
  dueCount: number
}

/**
 * The deck to offer as "continue".
 *
 * This is the last deck reviewed, or the first deck owned when nothing has been
 * reviewed yet. It does **not** mean a session is currently open — the API has no
 * such signal on this read, so it must not be treated as one.
 */
export interface RecentSession {
  nodeId: string
  deckTitle: string
  remainingCount: number
}

export interface DashboardStats {
  totalLearnedWords: number
  dueTodayCount: number
  masteryPercentage: number
  fsrsForecast: ForecastDay[]
  recentSession: RecentSession | null
}
