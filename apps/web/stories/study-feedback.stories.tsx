import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { PendingGradePanel } from "@/components/study/pending-grade-panel"
import { RoundBreakPanel } from "@/components/study/round-break-panel"
import { RoundIndicator } from "@/components/study/round-indicator"
import { VerdictPanel } from "@/components/study/verdict-panel"
import type { SingleChoiceReady } from "@/lib/api/types"
import type { Verdict } from "@/lib/study/session-machine"

/**
 * The study loop's feedback surfaces: the verdict a grade settles into, the
 * pending state a free-text answer waits in, the round pips, and the break panel.
 *
 * The verdict is deliberately shown in three shapes, because the component reads
 * three states out of one type: a correct rule-graded answer with a reveal and a
 * stage promotion, an incorrect one, and a rubric grade that settled with feedback
 * but no boolean — the case that must not render as "wrong".
 */
const meta = {
  title: "Study/Feedback",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

const question: SingleChoiceReady = {
  state: "ready",
  renderFormat: "single_choice",
  questionId: 1,
  senseId: 7,
  interactionMode: "assessment",
  requestedLevel: 3,
  servedLevel: 3,
  isFallback: false,
  payload: {
    stem: "Which word best completes the sentence?",
    options: ["compelling", "reluctant", "adjacent", "nominal"],
  },
}

const correct: Verdict = {
  isCorrect: true,
  score: 100,
  feedback: null,
  reveal: { correct_index: 0, correct_option: "compelling" },
  masteryBefore: 52,
  masteryAfter: 58,
}

const incorrect: Verdict = {
  isCorrect: false,
  score: 0,
  feedback: null,
  reveal: { correct_index: 0, correct_option: "compelling" },
  masteryBefore: 40,
  masteryAfter: 38,
}

const rubric: Verdict = {
  isCorrect: null,
  score: 70,
  feedback:
    "A clear sentence that shows you understand the word means short-lived. Consider a more vivid subject.",
  reveal: { feedback: "Good use of contrast to convey meaning." },
  masteryBefore: 31,
  masteryAfter: 33,
}

export const VerdictCorrect: Story = {
  render: () => (
    <VerdictPanel verdict={correct} renderFormat="single_choice" question={question} />
  ),
}

export const VerdictIncorrect: Story = {
  render: () => (
    <VerdictPanel verdict={incorrect} renderFormat="single_choice" question={question} />
  ),
}

/** A rubric grade with no boolean: neither correct nor wrong, just marked. */
export const VerdictRubric: Story = {
  render: () => <VerdictPanel verdict={rubric} renderFormat="free_text" />,
}

export const PendingMarking: Story = {
  render: () => <PendingGradePanel stale={false} failed={false} onReconnect={() => {}} />,
}

/** A denied re-subscribe: the only case that offers a reconnect. */
export const PendingStale: Story = {
  render: () => <PendingGradePanel stale failed={false} onReconnect={() => {}} />,
}

/** Terminal failure: no reconnect, because nothing is coming. */
export const PendingFailed: Story = {
  render: () => <PendingGradePanel stale={false} failed onReconnect={() => {}} />,
}

export const RoundPips: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <RoundIndicator roundIndex={0} served={3} maxPerRound={8} />
      <RoundIndicator roundIndex={2} served={8} maxPerRound={8} />
      {/* Cap unknown: only the round number shows, no invented denominator. */}
      <RoundIndicator roundIndex={1} served={4} maxPerRound={null} />
    </div>
  ),
}

export const RoundBreak: Story = {
  render: () => (
    <RoundBreakPanel roundIndex={2} answeredInRound={6} onContinue={() => {}} advancing={false} />
  ),
}

/** The empty round: a break reached with nothing answered reads differently. */
export const RoundBreakEmpty: Story = {
  render: () => (
    <RoundBreakPanel roundIndex={1} answeredInRound={0} onContinue={() => {}} advancing={false} />
  ),
}
