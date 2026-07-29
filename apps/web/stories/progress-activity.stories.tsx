import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { ActivityTaskRow } from "@/components/activity/activity-task-row"
import { CefrMixChart } from "@/components/progress/cefr-mix-chart"
import { MasteryDistribution } from "@/components/progress/mastery-distribution"
import { ReviewHistoryChart } from "@/components/progress/review-history-chart"
import { StatFigure } from "@/components/progress/stat-figure"
import { WeakestWordList } from "@/components/progress/weakest-word-list"
import type { HistoryBucket, WeakSense } from "@/lib/api/types"
import type { ActivityTask } from "@/lib/stores/activity-store"

/**
 * The progress figures and the activity feed rows.
 *
 * `StatFigure` is one of only two screens permitted a figure this size, and its
 * optional stage tint borrows the mastery ramp, so the stories show both a bare
 * count and a tinted percentage. `ActivityTaskRow` states the outcome of a piece
 * of async work, so every terminal tone plus the still-running and the
 * no-longer-watching states are pinned — those are the ones a review needs.
 */
const meta = {
  title: "Progress/Figures and Activity",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

export const Figures: Story = {
  render: () => (
    <div className="flex flex-wrap gap-10">
      <StatFigure label="Words learned" value="1,284" detail="across 12 decks" />
      <StatFigure label="Due today" value="37" />
      <StatFigure label="Retention" value="86%" detail="last 30 days" stage="4" />
      <StatFigure label="Mastery" value="Fluent" stage="5" />
    </div>
  ),
}

/** The average as a marked position on the ramp, plus the one count the API supplies. */
export const Mastery: Story = {
  render: () => (
    <div className="max-w-md">
      <MasteryDistribution avgMastery={47} learned={182} mastered={24} />
    </div>
  ),
}

/** Nothing reviewed yet: the ramp is withheld rather than drawn at zero. */
export const MasteryEmpty: Story = {
  render: () => (
    <div className="max-w-md">
      <MasteryDistribution avgMastery={0} learned={0} mastered={0} />
    </div>
  ),
}

/** One series, one colour: CEFR is an ordered scale, not six categories. */
export const CefrMix: Story = {
  render: () => (
    <div className="max-w-lg">
      <CefrMixChart distribution={{ A1: 12, A2: 34, B1: 58, B2: 41, C1: 19, C2: 4 }} />
    </div>
  ),
}

/** An unrecognised level keeps its own bar rather than being dropped. */
export const CefrMixWithUnknown: Story = {
  render: () => (
    <div className="max-w-lg">
      <CefrMixChart distribution={{ A2: 20, B1: 30, B2: 15, Uncategorised: 6 }} />
    </div>
  ),
}

const history: HistoryBucket[] = Array.from({ length: 30 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 5, 1 + index)).toISOString().slice(0, 10)
  // A quiet stretch mid-window, so the flat-carry-forward baseline is visible.
  const reviewed = index < 8 || index > 22 ? 0 : Math.round(6 + 10 * Math.sin(index))
  return { bucket: date, reviewed: Math.max(0, reviewed), avgMastery: 40 + index }
})

export const ReviewHistory: Story = {
  render: () => (
    <div className="max-w-lg">
      <ReviewHistoryChart history={history} />
    </div>
  ),
}

const weakest: WeakSense[] = [
  { senseId: 1, mastery: 8, word: "ephemeral", definition: "lasting for a very short time", pos: "adjective", cefrLevel: "C1" },
  { senseId: 2, mastery: 19, word: "ubiquitous", definition: "present, appearing, or found everywhere", pos: "adjective", cefrLevel: "C1" },
  // A row whose sense regenerated away upstream: score kept, headword gone.
  { senseId: 3, mastery: 25, word: null, definition: null, pos: null, cefrLevel: null },
]

export const WeakestFull: Story = {
  render: () => (
    <div className="max-w-lg">
      <WeakestWordList weakest={weakest} />
    </div>
  ),
}

/** The empty state ranks nothing yet and says why. */
export const WeakestEmpty: Story = {
  render: () => (
    <div className="max-w-lg">
      <WeakestWordList weakest={[]} />
    </div>
  ),
}

function task(overrides: Partial<ActivityTask> = {}): ActivityTask {
  return {
    taskId: "task-1",
    kind: "word-generation",
    senseId: null,
    label: "serendipity",
    status: "running",
    version: 1,
    errorCode: null,
    stale: false,
    ...overrides,
  }
}

export const ActivityRows: Story = {
  render: () => (
    <ul className="max-w-md divide-y divide-border">
      <ActivityTaskRow task={task({ status: "running" })} onDismiss={() => {}} />
      <ActivityTaskRow
        task={task({ taskId: "task-2", kind: "question-generation", senseId: 7, label: null, status: "queued" })}
        onDismiss={() => {}}
      />
      <ActivityTaskRow
        task={task({ taskId: "task-3", kind: "grade", senseId: 7, label: null, status: "succeeded" })}
        onDismiss={() => {}}
      />
      <ActivityTaskRow
        task={task({ taskId: "task-4", status: "failed", errorCode: "word_generation_quota_exceeded" })}
        onDismiss={() => {}}
      />
      <ActivityTaskRow
        task={task({ taskId: "task-5", status: "expired" })}
        onDismiss={() => {}}
      />
      <ActivityTaskRow
        task={task({ taskId: "task-6", status: "unknown", stale: true })}
        onDismiss={() => {}}
      />
    </ul>
  ),
}
