import Link from "next/link"

import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { WarningCircleIcon } from "@/lib/icons"

/**
 * The session ended for a reason that is not completion.
 *
 * Terminal on purpose: there is no retry here. The two codes that reach this screen
 * are a deck whose structure changed under the session and a session the server no
 * longer holds, and re-calling `/next` for either walks into the same rejection. So
 * the only actions are leaving and starting again.
 *
 * The message is passed in rather than derived, because the one case that matters
 * most needs a sentence the taxonomy cannot carry: a scope change is checked before
 * the answer is consumed, so an answer sent into it was never recorded, and the
 * learner has to be told that rather than left to assume it counted.
 */
export function SessionStoppedPanel({
  message,
  nodeId,
}: {
  message: string
  /** The deck to return to. Absent when the session's node is unknown. */
  nodeId: string | null
}) {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <WarningCircleIcon />
        </EmptyMedia>
        <EmptyTitle>Session ended</EmptyTitle>
        <EmptyDescription>{message}</EmptyDescription>
      </EmptyHeader>

      <div className="flex flex-wrap items-center justify-center gap-3">
        {nodeId ? (
          <Button render={<Link href={`/library/${nodeId}`} />}>Back to the deck</Button>
        ) : (
          <Button render={<Link href="/library" />}>Back to the library</Button>
        )}
      </div>
    </Empty>
  )
}
