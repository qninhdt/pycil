import { Spinner } from "@/components/ui/spinner"

/**
 * Placeholder while the session read resolves.
 *
 * A spinner rather than a skeleton of the question stage. Which surface comes next is
 * genuinely unknown at this point — a question, a break, a recap — so a skeleton
 * shaped like any one of them would be wrong more often than right, and a card
 * outline that becomes a recap reads as a glitch.
 */
export default function Loading() {
  return (
    <div className="flex min-h-[100dvh] items-center justify-center">
      <Spinner className="size-6 text-muted-foreground" aria-label="Loading your session" />
    </div>
  )
}
