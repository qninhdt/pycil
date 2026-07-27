import Link from "next/link"

import { Button } from "@/components/ui/button"
import { SignInIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

/**
 * What an anonymous visitor sees where a signed-in learner sees an action.
 *
 * Public decks and senses are readable without an account on purpose, so the
 * anonymous path is a first-class view rather than a wall: mutation affordances
 * are absent, and this states plainly what an account would add. A disabled
 * button would be worse — it advertises a control that cannot do anything.
 */
export function AnonymousCta({
  action,
  className,
}: {
  /** What signing in would let them do here, e.g. "add this word to a deck". */
  action: string
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-border p-4 sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <p className="text-sm text-muted-foreground">
        Sign in to {action}. Reading is open to everyone.
      </p>
      <Button render={<Link href="/login" />} className="shrink-0">
        <SignInIcon data-icon="inline-start" />
        Sign in
      </Button>
    </div>
  )
}
