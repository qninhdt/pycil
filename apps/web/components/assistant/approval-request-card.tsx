"use client"

import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import type { ActionDecision } from "@/lib/api/types"
import { ShieldCheckIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

/**
 * The human-in-the-loop gate for a destructive tool.
 *
 * The confirmable tools are move, publish, delete, and sense removal, so this card
 * is the last thing between a model's suggestion and a learner losing a deck. It is
 * written to be read: what will happen, and to what.
 *
 * Approval is never the quiet default. There is no pre-selected button, and the
 * destructive framing is on the approve control rather than the reject one. A paused
 * run holds nothing and never expires, so the offer stands until a decision is given.
 */

/** What each confirmable tool actually does, in the second person. */
const TOOL_EFFECT: Record<string, string> = {
  move_node: "move this into another folder",
  publish_node: "make this public, along with everything inside it",
  delete_node: "permanently delete this and everything inside it",
  remove_senses_from_deck: "remove words from the deck",
}

/** Which tools destroy or expose something, as opposed to merely rearranging it. */
const IRREVERSIBLE = new Set(["delete_node", "publish_node"])

export interface ApprovalRequest {
  key: string
  runId: string
  actionId: string
  tool: string
  targets: Record<string, string>
}

export function ApprovalRequestCard({
  approval,
  onDecide,
  disabled = false,
}: {
  approval: ApprovalRequest
  onDecide: (
    runId: string,
    actionId: string,
    decision: ActionDecision,
  ) => Promise<void>
  disabled?: boolean
}) {
  const [submitting, setSubmitting] = useState<ActionDecision | null>(null)

  const effect = TOOL_EFFECT[approval.tool] ?? "run an action on your library"
  const target = primaryTarget(approval.targets)
  const irreversible = IRREVERSIBLE.has(approval.tool)

  async function decide(decision: ActionDecision) {
    setSubmitting(decision)
    try {
      await onDecide(approval.runId, approval.actionId, decision)
    } catch {
      // The chat reports the request error; leave the decision available to retry.
    } finally {
      setSubmitting(null)
    }
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
          disabled={disabled || submitting !== null}
        >
          {submitting === "approve" ? <Spinner /> : null}
          {irreversible ? "Approve anyway" : "Approve"}
        </Button>
      </div>
    </div>
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
