import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { AssistantErrorNotice } from "@/components/assistant/assistant-error-notice"
import { AssistantMessage, UserMessage } from "@/components/assistant/streaming-message"
import { ToolCallTrace } from "@/components/assistant/tool-call-trace"
import type { AssistantTurn, ToolTurn, UserTurn } from "@/lib/assistant/transcript"

/**
 * The transcript's message pieces: the two chat bubbles, the collapsible tool
 * trace, and the error notice a failed run resolves into.
 *
 * The assistant bubble is shown mid-stream and settled, because the streaming
 * caret is a real state the composer keys off. The error notice is pinned for the
 * two codes the wire taxonomy cannot carry — a timeout that is worth retrying and
 * a crash that is not — since the retry affordance differs between them.
 */
const meta = {
  title: "Assistant/Transcript",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

const user: UserTurn = {
  kind: "user",
  key: "u1",
  content: "Which of my decks has the most words due today?",
}

const settled: AssistantTurn = {
  kind: "assistant",
  key: "a1",
  content:
    "Your Academic Word List has 18 words due today, more than any other deck. IELTS preparation is next with 6.",
  streaming: false,
}

const streaming: AssistantTurn = {
  kind: "assistant",
  key: "a2",
  content: "Looking through your decks now",
  streaming: true,
}

export const Conversation: Story = {
  render: () => (
    <div className="flex max-w-lg flex-col gap-4">
      <UserMessage turn={user} />
      <AssistantMessage turn={settled} />
    </div>
  ),
}

/** Mid-stream: text is growing, so a caret rather than a spinner. */
export const Streaming: Story = {
  render: () => (
    <div className="max-w-lg">
      <AssistantMessage turn={streaming} />
    </div>
  ),
}

const pendingTool: ToolTurn = { kind: "tool", key: "t1", tool: "search_word", result: null }
const settledTool: ToolTurn = {
  kind: "tool",
  key: "t2",
  tool: "list_deck_items",
  result:
    "Academic Word List: 240 items, 18 due.\nIELTS preparation: 96 items, 6 due.\nPhrasal verbs: 54 items, 0 due.",
}

export const ToolCalls: Story = {
  render: () => (
    <div className="flex max-w-lg flex-col gap-3">
      <ToolCallTrace turn={pendingTool} />
      <ToolCallTrace turn={settledTool} />
    </div>
  ),
}

/** A timeout: worth retrying on a smaller ask, so the retry control appears. */
export const ErrorRetryable: Story = {
  render: () => (
    <div className="max-w-lg">
      <AssistantErrorNotice code="deadline_exceeded" onRetry={() => {}} />
    </div>
  ),
}

/** A crash: the same request crashes the same way, so no retry is offered. */
export const ErrorTerminal: Story = {
  render: () => (
    <div className="max-w-lg">
      <AssistantErrorNotice code="execution_failed" onRetry={() => {}} />
    </div>
  ),
}
