import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { ContinueSessionCard } from "@/components/dashboard/continue-session-card"
import { DueSummary } from "@/components/dashboard/due-summary"
import { ForecastStrip } from "@/components/dashboard/forecast-strip"
import { WeakestPreview } from "@/components/dashboard/weakest-preview"
import type { ForecastDay, WeakSense } from "@/lib/api/types"

/**
 * The Today screen's cards.
 *
 * `ContinueSessionCard` is "where to pick up", not "a session that is open", so its
 * empty state (no decks yet) matters as much as its populated one. The forecast
 * scales bar heights to the busiest day rather than a fixed ceiling, so a quiet week
 * is shown with a story whose counts are small and uneven.
 */
const meta = {
  title: "Dashboard/Today",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

export const Summary: Story = {
  render: () => (
    <div className="max-w-2xl">
      <DueSummary dueTodayCount={18} masteryPercentage={62} totalLearnedWords={284} />
    </div>
  ),
}

/** Nothing due reads as "ahead of schedule", not as an error. */
export const SummaryNothingDue: Story = {
  render: () => (
    <div className="max-w-2xl">
      <DueSummary dueTodayCount={0} masteryPercentage={41} totalLearnedWords={120} />
    </div>
  ),
}

export const ContinueWithDue: Story = {
  render: () => (
    <div className="max-w-md">
      <ContinueSessionCard
        recentSession={{ nodeId: "1", deckTitle: "Academic Word List", remainingCount: 12 }}
        dueCount={12}
      />
    </div>
  ),
}

/** A deck with nothing due still offers studying ahead. */
export const ContinueStudyAhead: Story = {
  render: () => (
    <div className="max-w-md">
      <ContinueSessionCard
        recentSession={{ nodeId: "1", deckTitle: "IELTS band 8", remainingCount: 0 }}
        dueCount={0}
      />
    </div>
  ),
}

/** No decks at all: the card becomes a route into the library. */
export const ContinueEmpty: Story = {
  render: () => (
    <div className="max-w-md">
      <ContinueSessionCard recentSession={null} dueCount={0} />
    </div>
  ),
}

const forecast: ForecastDay[] = [
  { date: "2026-06-01", dueCount: 18 },
  { date: "2026-06-02", dueCount: 4 },
  { date: "2026-06-03", dueCount: 0 },
  { date: "2026-06-04", dueCount: 11 },
  { date: "2026-06-05", dueCount: 26 },
  { date: "2026-06-06", dueCount: 7 },
  { date: "2026-06-07", dueCount: 2 },
]

export const Forecast: Story = {
  render: () => (
    <div className="max-w-md">
      <ForecastStrip forecast={forecast} />
    </div>
  ),
}

const weakest: WeakSense[] = [
  { senseId: 1, mastery: 8, word: "ephemeral", definition: "lasting for a very short time", pos: "adjective", cefrLevel: "C1" },
  { senseId: 2, mastery: 22, word: "ubiquitous", definition: "found everywhere", pos: "adjective", cefrLevel: "C1" },
  { senseId: 3, mastery: 30, word: null, definition: null, pos: null, cefrLevel: null },
]

export const WeakestFive: Story = {
  render: () => (
    <div className="max-w-md">
      <WeakestPreview weakest={weakest} />
    </div>
  ),
}
