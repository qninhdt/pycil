"use client"

import { Area, AreaChart, CartesianGrid, Line, XAxis, YAxis } from "recharts"

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import type { HistoryBucket } from "@/lib/api/types"

/**
 * Reviews per day, with the average mastery those reviews left behind.
 *
 * Two series on purpose: volume alone says how hard someone worked, and mastery alone
 * says where they ended up. Together they answer the question the screen exists for,
 * which is whether the work is moving the number.
 *
 * The server returns a bucket for every day in the window, including untouched ones,
 * and carries the pre-window mastery baseline forward into them. So a flat stretch is
 * a real "nothing happened, nothing changed" rather than a gap this component has to
 * interpolate.
 */
const config = {
  reviewed: { label: "Reviews", color: "var(--color-chart-1)" },
  avgMastery: { label: "Average mastery", color: "var(--color-chart-2)" },
} satisfies ChartConfig

/** `YYYY-MM-DD` to a short day label. */
function dayLabel(bucket: string): string {
  // Parsed at UTC noon: a midnight UTC date shifts to the previous day for anyone
  // west of UTC, which would put every label one day off.
  return new Date(`${bucket}T12:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  })
}

export function ReviewHistoryChart({ history }: { history: HistoryBucket[] }) {
  if (history.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Review history appears here once you have studied on at least one day.
      </p>
    )
  }

  const reviewed = history.reduce((total, bucket) => total + bucket.reviewed, 0)

  if (reviewed === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No reviews in this period. Try a longer range, or study something today.
      </p>
    )
  }

  const data = history.map((bucket) => ({ ...bucket, label: dayLabel(bucket.bucket) }))

  return (
    <ChartContainer config={config} className="aspect-[2/1] w-full">
      <AreaChart accessibilityLayer data={data}>
        <CartesianGrid vertical={false} />
        <XAxis
          dataKey="label"
          tickLine={false}
          axisLine={false}
          tickMargin={8}
          // A 365-day window has far more days than labels that fit at 320px, so
          // Recharts drops the ones that would collide rather than overlapping them.
          interval="preserveStartEnd"
          minTickGap={24}
        />
        <YAxis
          yAxisId="reviews"
          allowDecimals={false}
          tickLine={false}
          axisLine={false}
          width={32}
          tickMargin={4}
        />
        {/* Mastery is a 0-100 score, so its axis is pinned to that domain rather than
            scaled to the data: an axis that rescales makes a two-point gain look like
            a breakthrough. */}
        <YAxis
          yAxisId="mastery"
          orientation="right"
          domain={[0, 100]}
          tickLine={false}
          axisLine={false}
          width={32}
          tickMargin={4}
        />
        <ChartTooltip content={<ChartTooltipContent />} />
        <Area
          yAxisId="reviews"
          dataKey="reviewed"
          type="monotone"
          fill="var(--color-reviewed)"
          fillOpacity={0.15}
          stroke="var(--color-reviewed)"
          strokeWidth={2}
        />
        <Line
          yAxisId="mastery"
          dataKey="avgMastery"
          type="monotone"
          stroke="var(--color-avgMastery)"
          strokeWidth={2}
          dot={false}
        />
      </AreaChart>
    </ChartContainer>
  )
}
