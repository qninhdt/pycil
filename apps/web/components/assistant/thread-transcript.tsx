"use client"

/**
 * One thread's conversation, rendered from folded turns.
 *
 * Scrolling belongs to `MessageScroller`, not to this file. The primitive already
 * follows a streaming tail, releases the follow when the reader scrolls up, and
 * offers a jump-to-latest button — and a hand-rolled stick-to-bottom effect would
 * fight it for the scroll position while tokens arrive.
 */

import { MessageGroup } from "@/components/ui/message"
import {
  MessageScroller,
  MessageScrollerButton,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { ChatCircleIcon } from "@/lib/icons"
import type { ActionDecision } from "@/lib/api/types"
import { assertNever } from "@/lib/assistant/exhaustive"
import type { Transcript, Turn } from "@/lib/assistant/transcript"

import { ApprovalRequestCard } from "./approval-request-card"
import { AssistantErrorNotice } from "./assistant-error-notice"
import { AssistantMessage, UserMessage } from "./streaming-message"
import { ToolCallTrace } from "./tool-call-trace"

export function ThreadTranscript({
  transcript,
  onDecide,
  deciding,
}: {
  transcript: Transcript
  onDecide: (runId: string, actionId: string, decision: ActionDecision) => void
  deciding: boolean
}) {
  if (transcript.turns.length === 0) {
    return (
      <Empty className="border-none">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <ChatCircleIcon />
          </EmptyMedia>
          <EmptyTitle>Ask about your library</EmptyTitle>
          <EmptyDescription>
            The assistant can find a word, build a deck, move things around, or tell you
            what a folder contains. Anything that changes or removes something asks you
            first.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <MessageScrollerProvider>
      <MessageScroller>
        <MessageScrollerViewport>
          <MessageScrollerContent className="px-4 py-4">
            {transcript.turns.map((turn, index) => (
              <MessageScrollerItem
                key={turn.key}
                // The last item is the scroll anchor, which is what gives the
                // primitive something to follow as tokens extend it.
                scrollAnchor={index === transcript.turns.length - 1}
              >
                <TurnRow turn={turn} onDecide={onDecide} deciding={deciding} />
              </MessageScrollerItem>
            ))}
          </MessageScrollerContent>
        </MessageScrollerViewport>
        <MessageScrollerButton />
      </MessageScroller>
    </MessageScrollerProvider>
  )
}

/**
 * One turn, dispatched on its kind.
 *
 * The switch is exhaustive over `Turn` and returns from every arm, so adding a turn
 * kind without rendering it fails the typecheck rather than silently rendering
 * nothing.
 */
function TurnRow({
  turn,
  onDecide,
  deciding,
}: {
  turn: Turn
  onDecide: (runId: string, actionId: string, decision: ActionDecision) => void
  deciding: boolean
}) {
  switch (turn.kind) {
    case "user":
      return <UserMessage turn={turn} />

    case "assistant":
      return <AssistantMessage turn={turn} />

    case "tool":
      return (
        <MessageGroup>
          <ToolCallTrace turn={turn} />
        </MessageGroup>
      )

    case "approval":
      return (
        <ApprovalRequestCard
          approval={turn}
          onDecide={onDecide}
          disabled={deciding}
        />
      )

    case "error":
      // The run's own failure code, which the taxonomy turns into a sentence. Not a
      // submission failure: that never became a transcript turn.
      return <AssistantErrorNotice code={turn.code} />

    default:
      // A turn kind with no arm above is a compile error here. Without this the
      // switch would simply fall through and return `undefined`, which React accepts
      // as a valid node — so a new kind would render as nothing at all, silently.
      return assertNever(turn, "transcript turn kind")
  }
}
