import { ContinueSessionCard } from "@/components/dashboard/continue-session-card"
import { DueSummary } from "@/components/dashboard/due-summary"
import { ForecastStrip } from "@/components/dashboard/forecast-strip"
import { WeakestPreview } from "@/components/dashboard/weakest-preview"
import { getTodayData } from "@/lib/actions/dashboard"

export const metadata = { title: "Today" }

/**
 * Today: what to study now, how much is due, and what is weakest.
 *
 * A read failure is left to `error.tsx` rather than caught here. Catching it
 * would mean rendering the frame around an apology, and the due count is the
 * whole reason to be on this screen — there is no useful partial Today.
 */
export default async function TodayPage() {
  const { stats, weakest } = await getTodayData()

  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      {/* Every other route names itself in a level-one heading; this one did not,
          which left the app's default landing page with no top-level heading at
          all. That is the one a screen reader announces on arrival and the anchor
          the rest of the document's outline hangs from, so its absence is a real
          defect rather than a stylistic choice — the cards below are `h3`s inside
          `CardTitle`, so without this the outline started mid-level. */}
      <h1 className="text-2xl tracking-tight">Today</h1>
      <DueSummary
        dueTodayCount={stats.dueTodayCount}
        masteryPercentage={stats.masteryPercentage}
        totalLearnedWords={stats.totalLearnedWords}
      />
      <ContinueSessionCard
        recentSession={stats.recentSession}
        dueCount={stats.dueTodayCount}
      />
      <ForecastStrip forecast={stats.fsrsForecast} />
      <WeakestPreview weakest={weakest} />
    </div>
  )
}
