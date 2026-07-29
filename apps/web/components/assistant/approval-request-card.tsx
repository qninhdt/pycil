"use client"

import { useCallback, useState, useSyncExternalStore } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import type { ActionDecision } from "@/lib/api/types"
import type { ApprovalTurn } from "@/lib/assistant/transcript"
import { ClockIcon, ShieldCheckIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

/**
 * The human-in-the-loop gate for a destructive tool.
 *
 * The confirmable tools are move, publish, delete, and sense removal, so this card
 * is the last thing between a model's suggestion and a learner losing a deck. It is
 * written to be read: what will happen, to what, and how long the offer stands.
 *
 * Approval is never the quiet default. There is no pre-selected button, the
 * destructive framing is on the approve control rather than the reject one, and an
 * expired request cannot be approved at all.
 */

/** What each confirmable tool actually does, in the second person. */
const TOOL_EFFECT: Record<string, string> = {
  move_node: "move this into another folder",
  publish_node: "make this public, along with everything inside it",
  delete_node: "permanently delete this and everything inside it",
  remove_sense_from_deck: "remove this word from the deck",
}

/** Which tools destroy or expose something, as opposed to merely rearranging it. */
const IRREVERSIBLE = new Set(["delete_node", "publish_node"])

export function ApprovalRequestCard({
  approval,
  onDecide,
  disabled = false,
}: {
  approval: ApprovalTurn
  onDecide: (runId: string, actionId: string, decision: ActionDecision) => void
  disabled?: boolean
}) {
  const expired = useHasExpired(approval.expiresAt)
  const [submitting, setSubmitting] = useState<ActionDecision | null>(null)

  const effect = TOOL_EFFECT[approval.tool] ?? "run an action on your library"
  const target = primaryTarget(approval.targets)
  const irreversible = IRREVERSIBLE.has(approval.tool)

  function decide(decision: ActionDecision) {
    setSubmitting(decision)
    onDecide(approval.runId, approval.actionId, decision)
  }

  return (
    <div
      // `group` rather than `alertdialog`: the run is already paused and the
      // transcript stays readable behind it, so trapping focus would stop the
      // learner scrolling up to see what they asked for before deciding.
      role="group"
      aria-labelledby={`${approval.key}-title`}
      className={cn(
        "flex flex-col gap-3 rounded-xl border px-4 py-3",
        irreversible ? "border-destructive/40 bg-destructive/5" : "border-border bg-muted/40",
      )}
    >
      <div className="flex items-start gap-2">
        <ShieldCheckIcon
          aria-hidden
          className={cn("mt-0.5 size-4 shrink-0", irreversible && "text-destructive")}
        />
        <div className="flex min-w-0 flex-col gap-1">
          <p id={`${approval.key}-title`} className="text-sm font-medium">
            The assistant wants to {effect}.
          </p>

          {/* The target is named on its own line, unabbreviated. A name truncated
              mid-word is how the wrong deck gets deleted. */}
          {target ? (
            <p className="text-sm wrap-break-word text-muted-foreground">
              <span className="font-serif font-semibold text-foreground">{target}</span>
            </p>
          ) : (
            // Never implied. If the server could not resolve a name — a target that
            // is gone, or an argument shape this build does not know — saying so is
            // more useful than showing a confident label for the wrong thing.
            <p className="text-sm text-muted-foreground">
              The exact target could not be confirmed. Reject this unless you are sure
              what you asked for.
            </p>
          )}
        </div>
      </div>

      <ExpiryLine expiresAt={approval.expiresAt} expired={expired} />

      <div className="flex flex-wrap items-center gap-2">
        <Button
          size="sm"
          variant="outline"
          onClick={() => decide("reject")}
          disabled={disabled || submitting !== null}
        >
          {submitting === "reject" ? <Spinner /> : null}
          Reject
        </Button>
        <Button
          size="sm"
          variant={irreversible ? "destructive" : "default"}
          onClick={() => decide("approve")}
          // Expiry disables only approval. Rejecting an expired request is still
          // worth allowing: it is how the learner dismisses it.
          disabled={disabled || expired || submitting !== null}
        >
          {submitting === "approve" ? <Spinner /> : null}
          {irreversible ? "Approve anyway" : "Approve"}
        </Button>
      </div>
    </div>
  )
}

/** The deadline, counted down while it is live and stated plainly once it is not. */
function ExpiryLine({ expiresAt, expired }: { expiresAt: string; expired: boolean }) {
  const remaining = useSecondsRemaining(expiresAt)

  if (expired) {
    return (
      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <ClockIcon aria-hidden className="size-3.5" />
        This request expired. Ask the assistant again if you still want it.
      </p>
    )
  }

  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <ClockIcon aria-hidden className="size-3.5" />
      {/* Announced politely rather than assertively: a per-second countdown read
          aloud on every tick would drown out the card itself. */}
      <span aria-live="polite">Expires in {formatRemaining(remaining)}</span>
    </p>
  )
}

/**
 * The most meaningful target among the tool's arguments.
 *
 * `node_id` and `deck_id` are the thing being acted on; `parent_id` is only the
 * destination of a move, so it is the last resort rather than the headline.
 */
function primaryTarget(targets: Record<string, string>): string | null {
  return targets.node_id ?? targets.deck_id ?? targets.parent_id ?? null
}

/**
 * Whether the deadline has passed, re-evaluated as it approaches.
 *
 * A card rendered once and never updated would keep an approve button live long
 * after the server stopped honouring it, so the learner would click and get a
 * rejection instead of an action.
 */
function useHasExpired(expiresAt: string): boolean {
  return useSecondsRemaining(expiresAt) <= 0
}

/**
 * Seconds left, ticking. Clamped at zero so the display never goes negative.
 *
 * The clock is external state, so it is read through `useSyncExternalStore` rather
 * than mirrored into `useState` from an effect. That is not only the lint rule's
 * preference: seeding state in an effect body means the first paint shows a stale
 * count, which for an expiry is the one value that must never be stale — a card
 * replayed from a transcript whose approval lapsed while the tab was closed would
 * briefly offer an approve button the server has already stopped honouring.
 *
 * Subscribing per deadline keeps the interval keyed to the value it counts down.
 */
function useSecondsRemaining(expiresAt: string): number {
  const deadline = new Date(expiresAt).getTime()

  const subscribe = useCallback(
    (onChange: () => void) => {
      // An unparseable deadline never changes: it reads as expired forever, so there
      // is nothing to tick.
      if (Number.isNaN(deadline)) return () => {}

      const timer = setInterval(() => {
        onChange()
        if (secondsUntil(deadline) <= 0) clearInterval(timer)
      }, 1000)

      return () => clearInterval(timer)
    },
    [deadline],
  )

  const snapshot = useCallback(() => secondsUntil(deadline), [deadline])

  // The server has no clock the client should trust here, and a countdown rendered
  // on the server would be wrong by the time it arrived. Zero means "expired", which
  // is the safe thing to render before hydration.
  const serverSnapshot = useCallback(() => 0, [])

  return useSyncExternalStore(subscribe, snapshot, serverSnapshot)
}

function secondsUntil(deadline: number): number {
  // An unparseable deadline is treated as expired. Failing closed here means a
  // malformed timestamp blocks an approval rather than granting an unbounded one.
  if (Number.isNaN(deadline)) return 0
  return Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
}

function formatRemaining(seconds: number): string {
  if (seconds >= 60) {
    const minutes = Math.floor(seconds / 60)
    return `${minutes} minute${minutes === 1 ? "" : "s"}`
  }
  return `${seconds} second${seconds === 1 ? "" : "s"}`
}
