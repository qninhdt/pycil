"use client"

import { useEffect, useState } from "react"

import { ContinueSessionCard } from "@/components/dashboard/continue-session-card"
import { DueSummary } from "@/components/dashboard/due-summary"
import { ForecastStrip } from "@/components/dashboard/forecast-strip"
import { WeakestPreview } from "@/components/dashboard/weakest-preview"
import { getTodayData, type TodayData } from "@/lib/actions/dashboard"
import { Spinner } from "@/components/ui/spinner"

export default function TodayPage() {
  const [data, setData] = useState<TodayData | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    void getTodayData().then(setData).catch(() => setFailed(true))
  }, [])

  if (failed) return <p className="text-sm text-muted-foreground">Today could not load. Try again.</p>
  if (!data) return <Spinner aria-label="Loading today" />

  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <h1 className="text-2xl tracking-tight">Today</h1>
      <DueSummary
        dueTodayCount={data.stats.dueTodayCount}
        masteryPercentage={data.stats.masteryPercentage}
        totalLearnedWords={data.stats.totalLearnedWords}
      />
      <ContinueSessionCard recentSession={data.stats.recentSession} dueCount={data.stats.dueTodayCount} />
      <ForecastStrip forecast={data.stats.fsrsForecast} />
      <WeakestPreview weakest={data.weakest} />
    </div>
  )
}
