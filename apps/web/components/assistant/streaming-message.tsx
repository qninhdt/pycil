import { Bubble, BubbleContent } from "@/components/ui/bubble"
import { Message, MessageContent } from "@/components/ui/message"
import { cn } from "@/lib/utils"

import type { AssistantTurn, UserTurn } from "@/lib/assistant/transcript"

/**
 * One side of the conversation, as a bubble.
 *
 * Both roles are here rather than in two files because they are the same component
 * with two variants, and splitting them would duplicate the bubble wiring to express
 * a difference of alignment.
 */
export function UserMessage({ turn }: { turn: UserTurn }) {
  return (
    <Message align="end">
      <MessageContent>
        <Bubble>
          <BubbleContent>{turn.content}</BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  )
}

/**
 * The assistant's reply, which may still be arriving.
 *
 * `streaming` drives a caret rather than a spinner: text is already on screen and
 * growing, so a spinner would claim nothing had happened yet. The caret is
 * `aria-hidden` because a screen reader announcing a blinking block on every token
 * would bury the words it sits next to.
 *
 * An empty streaming turn still renders. That gap between submitting and the first
 * token is where the model is thinking, and showing nothing there reads as a dropped
 * message.
 */
export function AssistantMessage({ turn }: { turn: AssistantTurn }) {
  return (
    <Message align="start">
      <MessageContent>
        <Bubble variant="muted">
          <BubbleContent>
            {turn.content}
            {turn.streaming ? (
              <span
                aria-hidden
                className={cn(
                  "ml-0.5 inline-block h-4 w-[2px] translate-y-0.5 bg-foreground/70",
                  "motion-safe:animate-pulse",
                )}
              />
            ) : null}
          </BubbleContent>
        </Bubble>
      </MessageContent>
    </Message>
  )
}
