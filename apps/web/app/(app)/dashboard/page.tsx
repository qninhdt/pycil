import { getDashboardStatsAction } from "@/lib/actions/dashboard";
import { DashboardMetricsGrid } from "@/components/dashboard/dashboard-metrics-grid";
import { FSRSForecastChart } from "@/components/dashboard/fsrs-forecast-chart";
import { QuickContinueCard } from "@/components/dashboard/quick-continue-card";
import { WeakestWordsCard } from "@/components/dashboard/weakest-words-card";

export const metadata = {
  title: "Dashboard - Pycil",
  description: "Overview of your vocabulary learning progress and FSRS review forecast.",
};

export default async function DashboardPage() {
  const stats = await getDashboardStatsAction();

  const fallbackStats = stats || {
    totalLearnedWords: 0,
    dueTodayCount: 0,
    masteryPercentage: 0,
    fsrsForecast: Array.from({ length: 7 }, (_, i) => {
      const d = new Date();
      d.setDate(d.getDate() + i);
      return { date: d.toISOString().split("T")[0], dueCount: 0 };
    }),
    recentSession: null,
  };

  return (
    <div className="p-6 md:p-8 max-w-7xl mx-auto space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-neutral-900 dark:text-neutral-100">
          Learning Dashboard
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          Track your vocabulary mastery, daily review forecast, and recent study sessions.
        </p>
      </div>

      {/* Quick Action Banner */}
      <QuickContinueCard recentSession={fallbackStats.recentSession} />

      {/* Metric Cards Grid */}
      <DashboardMetricsGrid stats={fallbackStats} />

      {/* Weakest Words Spotlight */}
      <WeakestWordsCard nodeId={fallbackStats.recentSession?.nodeId} />

      {/* FSRS Forecast Chart */}
      <FSRSForecastChart forecast={fallbackStats.fsrsForecast} />
    </div>
  );
}
