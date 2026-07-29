import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card"
import { Empty, EmptyDescription, EmptyTitle } from "@/components/ui/empty"
import type { FolderStats, NodeRead } from "@/lib/api/types"
import { masteryStageAttr } from "@/lib/design/mastery"

import { CreateNodeSheet } from "./create-node-sheet"
import { NodeList } from "./node-list"
import { NodeHeader } from "./node-header"

/**
 * A folder: what it contains, and how the words beneath it are doing.
 *
 * Figures only. The charts for the same numbers live on Progress, so putting them
 * here as well would mean two surfaces to keep honest about one dataset.
 *
 * `stats` is null for a reader with no learning state beneath this folder, which is
 * what an anonymous visitor to a public folder sees. The block is omitted rather
 * than rendered as four zeros, because zero words learned and no account are
 * different statements.
 */
export function FolderView({
  node,
  childNodes,
  stats,
  canEdit,
}: {
  node: NodeRead
  /**
   * The folder's direct children, already fetched by the route.
   *
   * Named `childNodes` rather than `children` on purpose: `children` on a React
   * component means rendered content, and a caller reading this JSX would expect
   * these nodes to be nested inside the tag rather than passed as data.
   */
  childNodes: NodeRead[]
  stats: FolderStats | null
  canEdit: boolean
}) {
  return (
    <div className="flex flex-col gap-6">
      <NodeHeader node={node} canEdit={canEdit}>
        {canEdit ? <CreateNodeSheet parentNodeId={node.id} /> : null}
      </NodeHeader>

      {stats && stats.total > 0 ? <FolderStatsRow stats={stats} /> : null}

      {childNodes.length === 0 ? (
        <Empty>
          <EmptyTitle>Nothing in here yet</EmptyTitle>
          <EmptyDescription>
            {canEdit
              ? "Add a deck to start collecting words, or a folder to group them."
              : "This folder is empty."}
          </EmptyDescription>
          {canEdit ? (
            <CreateNodeSheet parentNodeId={node.id} />
          ) : null}
        </Empty>
      ) : (
        <NodeList nodes={childNodes} />
      )}
    </div>
  )
}

/**
 * The four aggregate figures for a folder's subtree.
 *
 * `learned` and `mastered` are server-computed thresholds from the learning policy.
 * The UI reports them and does not re-derive either, so "mastered" cannot mean one
 * thing here and another in the API's own statistics.
 */
function FolderStatsRow({ stats }: { stats: FolderStats }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <StatCell label="Words" value={String(stats.total)} />
      <StatCell label="Learned" value={String(stats.learned)} />
      <StatCell label="Mastered" value={String(stats.mastered)} />
      <StatCell
        label="Average mastery"
        value={`${Math.round(stats.avgMastery)}%`}
        stage={masteryStageAttr(stats.avgMastery)}
      />
    </div>
  )
}

function StatCell({
  label,
  value,
  stage,
}: {
  label: string
  value: string
  /** Present only on the one figure that carries a mastery colour. */
  stage?: string
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1">
        <CardDescription>{label}</CardDescription>
        <CardTitle
          className={stage ? "stage-text text-2xl tabular-nums" : "text-2xl tabular-nums"}
          data-stage={stage}
        >
          {value}
        </CardTitle>
      </CardContent>
    </Card>
  )
}
