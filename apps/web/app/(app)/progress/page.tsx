"use client"

import { useSearchParams } from "next/navigation"
import { useEffect, useState } from "react"

import { ForecastStrip } from "@/components/dashboard/forecast-strip"
import { CefrMixChart } from "@/components/progress/cefr-mix-chart"
import { HistoryRangeSelector } from "@/components/progress/history-range-selector"
import { MasteryDistribution } from "@/components/progress/mastery-distribution"
import { ReviewHistoryChart } from "@/components/progress/review-history-chart"
import { ScopeSelector } from "@/components/progress/scope-selector"
import { StatFigure } from "@/components/progress/stat-figure"
import { WeakestWordList } from "@/components/progress/weakest-word-list"
import { readProgressData, type ProgressData } from "@/lib/actions/progress-reads"
import { masteryStageAttr } from "@/lib/design/mastery"
import { parseHistoryDays } from "@/lib/progress/history-window"
import { Spinner } from "@/components/ui/spinner"

export default function ProgressPage() {
  const params = useSearchParams()
  const nodeId = params.get("node")
  const days = parseHistoryDays(params.get("days") ?? undefined)
  const key = `${nodeId ?? "account"}:${days}`
  const [result, setResult] = useState<{ key: string; data: ProgressData | null; failed: boolean } | null>(null)

  useEffect(() => {
    void readProgressData(nodeId, days, new Date())
      .then((data) => setResult({ key, data, failed: false }))
      .catch(() => setResult({ key, data: null, failed: true }))
  }, [key, nodeId, days])

  if (!result || result.key !== key) return <Spinner aria-label="Loading progress" />
  if (result.failed || !result.data) return <p className="text-sm text-muted-foreground">Progress could not load. Try again.</p>
  const data = result.data

  const scopeName = nodeId ? (data.folders.find((folder) => folder.id === nodeId)?.name ?? "this folder") : null
  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <header className="flex flex-col gap-4">
        <h1 className="text-2xl tracking-tight">Progress</h1>
        <ScopeSelector folders={data.folders} nodeId={nodeId} />
      </header>
      {data.stats.total === 0 ? (
        <p className="max-w-prose text-sm text-muted-foreground">
          {scopeName ? `${scopeName} has no words yet, so there is nothing to measure.` : "You have no words yet, so there is nothing to measure."}
        </p>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-6 sm:grid-cols-4">
            <StatFigure label="Words" value={String(data.stats.total)} />
            <StatFigure label="Studied" value={String(data.stats.learned)} />
            <StatFigure label="Mastered" value={String(data.stats.mastered)} />
            <StatFigure label="Average" value={`${Math.round(data.stats.avgMastery)}%`} stage={masteryStageAttr(data.stats.avgMastery)} />
          </section>
          <MasteryDistribution avgMastery={data.stats.avgMastery} learned={data.stats.learned} mastered={data.stats.mastered} />
          {data.forecast ? <ForecastStrip forecast={data.forecast} /> : null}
          <section className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-sm font-medium text-muted-foreground">Review history</h2>
              <HistoryRangeSelector days={days} />
            </div>
            {data.historyError ? <p className="text-sm text-muted-foreground">{data.historyError}</p> : <ReviewHistoryChart history={data.history} />}
          </section>
          <CefrMixChart distribution={data.cefr} />
          <section className="flex flex-col gap-3">
            <h2 className="text-sm font-medium text-muted-foreground">Needs the most work</h2>
            <WeakestWordList weakest={data.weakest} />
          </section>
        </>
      )}
    </div>
  )
}
