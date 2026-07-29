"use client"

import { useRouter, useSearchParams } from "next/navigation"

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { HISTORY_PRESETS, type HistoryPreset } from "@/lib/progress/history-window"

/** How each preset reads to a person. A number of days is not a useful label. */
const LABELS: Record<HistoryPreset, string> = {
  7: "Week",
  30: "Month",
  90: "3 months",
  365: "Year",
}

/**
 * How far back the review history reaches.
 *
 * The range lives in the URL rather than in component state, so the server does the
 * fetching: the history read is scoped by date, and holding the range on the client
 * would mean either refetching from the browser or shipping a year of buckets and
 * filtering them locally.
 *
 * Only the four presets are offered. The API rejects a window over 365 days, and a
 * free date picker would let a learner build a request that can only fail.
 */
export function HistoryRangeSelector({ days }: { days: HistoryPreset }) {
  const router = useRouter()
  const searchParams = useSearchParams()

  function select(next: string) {
    const params = new URLSearchParams(searchParams)
    params.set("days", next)
    // `scroll: false` because this control sits well down the page: jumping to the
    // top on every range change would hide the chart the learner just adjusted.
    router.push(`?${params.toString()}`, { scroll: false })
  }

  return (
    <ToggleGroup
      value={[String(days)]}
      onValueChange={(value) => {
        const next = value[0]
        if (typeof next === "string") select(next)
      }}
      variant="outline"
      aria-label="History range"
    >
      {HISTORY_PRESETS.map((preset) => (
        <ToggleGroupItem key={preset} value={String(preset)}>
          {LABELS[preset]}
        </ToggleGroupItem>
      ))}
    </ToggleGroup>
  )
}
