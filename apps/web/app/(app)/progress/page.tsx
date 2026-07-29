import { ForecastStrip } from "@/components/dashboard/forecast-strip"
import { CefrMixChart } from "@/components/progress/cefr-mix-chart"
import { HistoryRangeSelector } from "@/components/progress/history-range-selector"
import { MasteryDistribution } from "@/components/progress/mastery-distribution"
import { ReviewHistoryChart } from "@/components/progress/review-history-chart"
import { ScopeSelector } from "@/components/progress/scope-selector"
import { StatFigure } from "@/components/progress/stat-figure"
import { WeakestWordList } from "@/components/progress/weakest-word-list"
import { readProgressData } from "@/lib/actions/progress-reads"
import { masteryStageAttr } from "@/lib/design/mastery"
import { parseHistoryDays } from "@/lib/progress/history-window"

export const metadata = { title: "Progress" }

/**
 * How the learner's vocabulary is actually developing.
 *
 * Both controls live in the URL rather than in client state, which is what keeps this a
 * server component: the scope and the range are read from the query, the reads happen
 * once, and a link to a particular view is shareable and survives a reload.
 *
 * Every figure comes from the server. The one number that used to be computed in two
 * places is "mastered", and it is now derived from a single floor in the API's learning
 * policy, so the count here and the stage on the ramp cannot disagree.
 */
export default async function ProgressPage({
  searchParams,
}: {
  searchParams: Promise<{ node?: string; days?: string }>
}) {
  const { node, days: daysParam } = await searchParams
  const nodeId = node ?? null
  const days = parseHistoryDays(daysParam)

  // One clock reading for the whole render, taken here rather than inside the window
  // helper so the request and every label derived from it agree.
  const data = await readProgressData(nodeId, days, new Date())

  const scopeName = nodeId
    ? (data.folders.find((folder) => folder.id === nodeId)?.name ?? "this folder")
    : null

  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <header className="flex flex-col gap-4">
        <h1 className="text-2xl tracking-tight">Progress</h1>
        <ScopeSelector folders={data.folders} nodeId={nodeId} />
      </header>

      {data.stats.total === 0 ? (
        <p className="max-w-prose text-sm text-muted-foreground">
          {scopeName
            ? `${scopeName} has no words yet, so there is nothing to measure. Add some words to a deck inside it and this screen fills in.`
            : "You have no words yet, so there is nothing to measure. Add a few to a deck and this screen fills in as you review them."}
        </p>
      ) : (
        <>
          {/* Four figures rather than a chart: these are single numbers, and a gauge
              per number is decoration with a legend. */}
          <section className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <StatFigure label="Words" value={String(data.stats.total)} />
            <StatFigure label="Studied" value={String(data.stats.learned)} />
            <StatFigure label="Fluent" value={String(data.stats.mastered)} />
            <StatFigure
              label="Average"
              value={`${Math.round(data.stats.avgMastery)}%`}
              stage={masteryStageAttr(data.stats.avgMastery)}
            />
          </section>

          <MasteryDistribution
            avgMastery={data.stats.avgMastery}
            learned={data.stats.learned}
            mastered={data.stats.mastered}
          />

          {/* Account-wide only: the forecast endpoint has no folder scope, and showing
              account figures under a folder heading would misattribute them. */}
          {data.forecast ? <ForecastStrip forecast={data.forecast} /> : null}

          <section className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-medium text-muted-foreground">
                Review history
              </h2>
              <HistoryRangeSelector days={days} />
            </div>

            {data.historyError ? (
              <p className="text-sm text-muted-foreground">{data.historyError}</p>
            ) : (
              <ReviewHistoryChart history={data.history} />
            )}
          </section>

          <CefrMixChart distribution={data.cefr} />

          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-muted-foreground">
              Needs the most work
            </h2>
            <WeakestWordList weakest={data.weakest} />
          </section>
        </>
      )}
    </div>
  )
}
