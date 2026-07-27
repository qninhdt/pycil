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
