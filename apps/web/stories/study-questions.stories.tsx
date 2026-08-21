import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { ExposureCard } from "@/components/study/exposure-card"
import { FreeTextQuestion } from "@/components/study/free-text-question"
import { SingleChoiceQuestion } from "@/components/study/single-choice-question"
import { TextSpanQuestion } from "@/components/study/text-span-question"
import type {
  FlashcardReady,
  FreeTextReady,
  SingleChoiceReady,
  TextSpanReady,
} from "@/lib/api/types"

/**
 * The four answer formats plus the exposure card, in isolation.
 *
 * Each is a controlled input driven by the session runner: it renders a question
 * and reports a choice, and never decides correctness. The stories hold the
 * selection in local state so the interaction is real, and pin a `disabled`
 * variant because that is the state every one of these enters the moment an answer
 * is submitted — the state a review most needs to see is not the resting one.
 */
const meta = {
  title: "Study/Question Formats",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

const base = {
  state: "ready",
  questionId: 1,
  senseId: 7,
  interactionMode: "assessment",
  requestedLevel: 3,
  servedLevel: 3,
  isFallback: false,
} as const

const singleChoice: SingleChoiceReady = {
  ...base,
  renderFormat: "single_choice",
  payload: {
    stem: "Which word best completes the sentence: “The evidence was ___ enough to convince the jury.”",
    options: ["compelling", "reluctant", "adjacent", "nominal"],
  },
}

const textSpan: TextSpanReady = {
  ...base,
  renderFormat: "text_span",
  payload: {
    stem_with_blank: "The committee reached a ___ after hours of debate.",
    word_bank: ["consensus", "consensual", "consent", "consented"],
  },
}

const freeText: FreeTextReady = {
  ...base,
  renderFormat: "free_text",
  payload: { prompt: "Use the word “ephemeral” in a sentence that makes its meaning clear." },
}

const flashcard: FlashcardReady = {
  ...base,
  renderFormat: "flashcard",
  questionId: null,
  interactionMode: "exposure",
  payload: {
    word: "serendipity",
    definition: "the occurrence of events by chance in a happy or beneficial way",
    pos: "noun",
    example: "A fortunate stroke of serendipity brought the two old friends together.",
    ipa_uk: "/ˌser.ənˈdɪp.ə.ti/",
    ipa_us: "/ˌser.ənˈdɪp.ə.t̬i/",
  },
}

/**
 * The interactive shells are components, not inline `render` closures: a hook
 * called in a bare `render` function breaks the rules-of-hooks lint, and a story
 * that holds real selection state is worth more than a static one.
 */
function SingleChoiceShell() {
  const [selected, setSelected] = useState<number | null>(null)
  return (
    <SingleChoiceQuestion
      question={singleChoice}
      selected={selected}
      onSelect={setSelected}
      disabled={false}
    />
  )
}

function TextSpanShell() {
  const [selected, setSelected] = useState<string | null>(null)
  return (
    <TextSpanQuestion
      question={textSpan}
      selected={selected}
      onSelect={setSelected}
      disabled={false}
    />
  )
}

function FreeTextShell({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial)
  return (
    <FreeTextQuestion question={freeText} value={value} onChange={setValue} disabled={false} />
  )
}

export const SingleChoice: Story = {
  render: () => <SingleChoiceShell />,
}

export const TextSpan: Story = {
  render: () => <TextSpanShell />,
}

export const FreeText: Story = {
  render: () => <FreeTextShell />,
}

/** The character counter appears only as the server's limit comes into range. */
export const FreeTextNearLimit: Story = {
  render: () => <FreeTextShell initial={"x".repeat(9600)} />,
}

/** Submitted: every input locks while the answer is in flight. */
export const Disabled: Story = {
  render: () => (
    <SingleChoiceQuestion
      question={singleChoice}
      selected={0}
      onSelect={() => {}}
      disabled
    />
  ),
}

export const Exposure: Story = {
  render: () => (
    <ExposureCard question={flashcard} onAdvance={() => {}} />
  ),
}
