import { createApiClient, type ApiClient } from "@/lib/api/client"
import { ApiError } from "@/lib/api/errors"
import type {
  CefrDistribution,
  DashboardStats,
  FolderStats,
  HistoryBucket,
  NodeRead,
  WeakSense,
} from "@/lib/api/types"
import { historyWindow, type HistoryPreset } from "@/lib/progress/history-window"

/**
 * The Progress screen's reads, at either scope.
 *
 * Plain browser reads over the direct API; no proxy endpoint is needed.
 *
 * The same five shapes are served at two scopes by one route each: `/v1/me/...`
 * with an optional `nodeId` query parameter. Absent means the whole account,
 * present means that folder's readable subtree, so one reader covers both and the
 * scope only picks the parameter. Fanning out over roots on the client was
 * rejected: a sense in two decks would be counted twice, which is why the API
 * resolves its sense set with `SELECT DISTINCT`.
 */

export interface ProgressData {
  stats: FolderStats
  history: HistoryBucket[]
  cefr: CefrDistribution
  weakest: WeakSense[]
  /**
   * Null at folder scope. The forecast is served only for the whole account, so a
   * folder view omits it rather than showing account-wide figures under a folder
   * heading.
   */
  forecast: DashboardStats["fsrsForecast"] | null
  /** Set when the history window was rejected, so the chart can say why. */
  historyError: string | null
  /** Root folders, for the scope selector. */
  folders: NodeRead[]
}

export async function readProgressData(
  nodeId: string | null,
  days: HistoryPreset,
  asOf: Date,
): Promise<ProgressData> {
  const client = createApiClient()
  const { from, to } = historyWindow(days, asOf)

  // Every read is independent, so they overlap rather than queue. The history read is
  // the only one allowed to fail softly, because a rejected window is a fixable
  // choice on this screen rather than a broken page.
  const [stats, history, cefr, weakest, forecast, folders] = await Promise.all([
    nodeId ? client.analytics.getFolderStats(nodeId) : client.analytics.getGlobalStats(),
    readHistory(client, nodeId, from, to),
    nodeId ? client.analytics.getFolderCefr(nodeId) : client.analytics.getGlobalCefr(),
    nodeId
      ? client.analytics.getFolderWeakest(nodeId, 10)
      : client.analytics.getGlobalWeakest(10),
    nodeId ? null : client.analytics.getDashboard(),
    readRootFolders(client),
  ])

  return {
    stats,
    history: history.buckets,
    cefr,
    weakest,
    forecast: forecast?.fsrsForecast ?? null,
    historyError: history.error,
    folders,
  }
}

/**
 * The history buckets, or the reason there are none.
 *
 * `history_window_invalid` is the one error this screen can act on: the range is a
 * control the learner just used, so the answer is to say the range was refused rather
 * than to render an empty chart that looks like "you studied nothing". The presets are
 * inside the API's limits, so reaching this means a hand-edited parameter.
 */
async function readHistory(
  client: ApiClient,
  nodeId: string | null,
  from: string,
  to: string,
): Promise<{ buckets: HistoryBucket[]; error: string | null }> {
  try {
    const buckets = nodeId
      ? await client.analytics.getFolderHistory(nodeId, from, to)
      : await client.analytics.getGlobalHistory(from, to)
    return { buckets, error: null }
  } catch (error) {
    if (error instanceof ApiError && error.code === "history_window_invalid") {
      return {
        buckets: [],
        error: "That date range was not accepted. Pick one of the ranges above.",
      }
    }
    throw error
  }
}

/** Root folders only. Decks have no analytics endpoints, so they cannot be a scope. */
async function readRootFolders(client: ApiClient): Promise<NodeRead[]> {
  const page = await client.hierarchy.listNodes(null)
  return page.items.filter((node) => node.type === "FOLDER")
}
