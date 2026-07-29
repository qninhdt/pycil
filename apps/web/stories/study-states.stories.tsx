import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { CalibrationNote } from "@/components/study/calibration-note"
import { PreparingPanel, SettlingPanel, StalledPanel } from "@/components/study/polling-panel"
import { QuestionStage } from "@/components/study/question-stage"
import { RevealDisplay } from "@/components/study/reveal-display"
import { SessionRecap } from "@/components/study/session-recap"
import { SessionStoppedPanel } from "@/components/study/session-stopped-panel"
import type { SessionState, SingleChoiceReady } from "@/lib/api/types"

/**
 * The study loop's non-question surfaces: the two polled waits and the stall they
 * both land in, the fallback calibration note, the answer reveal, the durable
 * recap, and the terminal stopped panel.
 *
 * These are the states a review most needs and a happy-path demo never shows: a
 * session waiting on generation, a correct answer that still counts as a miss
 * because the server had to substitute an easier question, and a session that
 * ended because the deck changed underneath it.
 */
const meta = {
  title: "Study/States",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

export const Preparing: Story = {
  render: () => <PreparingPanel attempt={3} />,
}

export const Settling: Story = {
  render: () => <SettlingPanel attempt={2} />,
}

export const Stalled: Story = {
  render: () => (
    <StalledPanel
      message="Your next question is still being written. This sometimes takes a while."
      onRetry={() => {}}
      onLeave={() => {}}
      retrying={false}
    />
  ),
}

/**
 * The fallback note. It only renders when the server had to substitute the
 * requested difficulty, and it states plainly that the answer counts as a miss.
 */
export const CalibrationEasier: Story = {
  render: () => <CalibrationNote requestedLevel={3} servedLevel={1} isFallback />,
}

/** A same-level substitution: still a fallback, worded as "different" not "easier". */
export const CalibrationSubstitute: Story = {
  render: () => <CalibrationNote requestedLevel={2} servedLevel={2} isFallback />,
}

const choiceQuestion: SingleChoiceReady = {
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

export const RevealChoice: Story = {
  render: () => (
    <RevealDisplay
      renderFormat="single_choice"
      reveal={{ correct_index: 0, correct_option: "compelling" }}
      question={choiceQuestion}
    />
  ),
}

/** A span reveal names the accepted answer plus the inflections that also counted. */
export const RevealSpan: Story = {
  render: () => (
    <RevealDisplay
      renderFormat="text_span"
      reveal={{ correct_answer: "consensus", accepted_forms: ["consensuses"] }}
    />
  ),
}

export const RevealFreeText: Story = {
  render: () => (
    <RevealDisplay
      renderFormat="free_text"
      reveal={{ feedback: "Good use of contrast to convey the word's meaning." }}
    />
  ),
}

const recap: SessionState = {
  sessionId: "s1",
  status: "completed",
  nodeId: "deck-1",
  sensesAdmitted: 10,
  sensesCompleted: 8,
  sensesExhausted: 2,
  answersTotal: 24,
  answersCorrect: 19,
  roundsUsed: 3,
}

export const Recap: Story = {
  render: () => <SessionRecap session={recap} nodeId="deck-1" />,
}

/** A clean session: no "out of retries" figure when nothing was exhausted. */
export const RecapClean: Story = {
  render: () => (
    <SessionRecap
      session={{
        sessionId: "s2",
        status: "completed",
        nodeId: "deck-1",
        sensesAdmitted: 6,
        sensesCompleted: 6,
        sensesExhausted: 0,
        answersTotal: 12,
        answersCorrect: 12,
        roundsUsed: 2,
      }}
      nodeId="deck-1"
    />
  ),
}

/** The deck changed mid-session: terminal, and the answer in flight was not recorded. */
export const Stopped: Story = {
  render: () => (
    <SessionStoppedPanel
      message="This deck changed while you were studying, so the session ended. Your last answer was not recorded; everything before it was."
      nodeId="deck-1"
    />
  ),
}

/** The stage frame, with a header and a footer control, as the runner composes it. */
export const Stage: Story = {
  parameters: { layout: "fullscreen" },
  render: () => (
    <QuestionStage
      header={<span className="text-xs text-muted-foreground uppercase">Round 2</span>}
      footer={<span className="text-sm text-muted-foreground">Submit lives here</span>}
    >
      <p className="text-lg">The question body owns the vertical middle of the stage.</p>
    </QuestionStage>
  ),
}
