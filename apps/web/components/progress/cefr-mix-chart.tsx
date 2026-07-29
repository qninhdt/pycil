"use client"

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import type { CefrDistribution } from "@/lib/api/types"

/**
 * How the tracked vocabulary spreads across CEFR levels.
 *
 * The response is an open map, not an enum: which levels appear depends on the data
 * the dictionary holds, so the order comes from a known sequence with anything
 * unrecognised appended rather than dropped. A level the upstream source adds later
 * still renders, at the end, instead of vanishing from the chart.
 *
 * One series, one colour. Six bars in six hues would imply six unrelated categories
 * when CEFR is an ordered scale, and the design system forbids introducing a palette
 * outside the token layer.
 */
const CEFR_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"] as const

const config = {
  count: { label: "Words", color: "var(--color-chart-1)" },
} satisfies ChartConfig

export function CefrMixChart({ distribution }: { distribution: CefrDistribution }) {
  const known = CEFR_ORDER.filter((level) => distribution[level] != null).map((level) => ({
    level,
    count: distribution[level],
  }))

  // Anything the dictionary reports that is not in the standard sequence keeps its
  // own bar rather than being silently discarded.
  const extra = Object.keys(distribution)
    .filter((level) => !CEFR_ORDER.includes(level as (typeof CEFR_ORDER)[number]))
    .sort()
    .map((level) => ({ level, count: distribution[level] }))

  const data = [...known, ...extra]

  if (data.length === 0) {
    return (
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-medium text-muted-foreground">Level mix</h2>
        <p className="text-sm text-muted-foreground">
          Levels appear once your decks hold words the dictionary has graded.
        </p>
      </section>
    )
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-medium text-muted-foreground">Level mix</h2>

      <ChartContainer config={config} className="aspect-[2/1] w-full">
        <BarChart accessibilityLayer data={data}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="level" tickLine={false} axisLine={false} tickMargin={8} />
          {/* Integer ticks only: half a word is not a quantity. */}
          <YAxis
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            width={32}
            tickMargin={4}
          />
          <ChartTooltip content={<ChartTooltipContent />} />
          <Bar dataKey="count" fill="var(--color-count)" radius={4} />
        </BarChart>
      </ChartContainer>
    </section>
  )
}
