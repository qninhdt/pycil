"use client"

import { useState, useTransition } from "react"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogMedia,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Empty, EmptyDescription, EmptyTitle } from "@/components/ui/empty"
import { toast } from "@/components/ui/toast"
import { MinusIcon, WarningIcon } from "@/lib/icons"
import { removeSenseFromDeck } from "@/lib/actions/nodes"
import type { SenseContent } from "@/lib/api/types"
import { toastApiError } from "@/lib/feedback/toast-api-error"
import type { LiveSession } from "@/lib/stores/ui-store"
import { useUiStore } from "@/lib/stores/store-provider"

import { AddWordAction } from "./add-word-action"
import { DeckItemRow } from "./deck-item-row"

/**
 * A deck's words, with removal.
 *
 * Removal is a client island because it confirms first and the confirmation has to
 * say what is actually lost. Removing a sense from a deck discards the learning
 * history for that sense in that deck, and it bumps the deck's structural
 * generation — which ends a live session the same way an add does.
 */
export function DeckItemList({
  nodeId,
  ancestorIds,
  items,
  asOf,
  canEdit,
}: {
  nodeId: string
  /**
   * This deck's ancestors, root-first. A generation bump propagates upward, so a
   * session scoped to an ancestor folder is invalidated by a change here — while a
   * session on an unrelated deck is not. Comparing against the chain is what keeps
   * the warning honest in both directions.
   */
  ancestorIds: string[]
  items: SenseContent[]
  /** The instant "due now" is judged against, taken once on the server. */
  asOf: number
  /** False for a public deck someone else owns, and for an anonymous reader. */
  canEdit: boolean
}) {
  const liveSession = useUiStore((state) => state.liveSession)
  const setLiveSession = useUiStore((state) => state.setLiveSession)
  const [pending, setPending] = useState<SenseContent | null>(null)
  const [isRemoving, startRemoving] = useTransition()

  // Only a session covering this deck is affected. `liveSession` alone would also
  // fire for a session on a sibling deck, which this removal cannot touch.
  const affectedSession =
    liveSession &&
    (liveSession.nodeId === nodeId || ancestorIds.includes(liveSession.nodeId))
      ? liveSession
      : null

  if (items.length === 0) {
    return (
      <Empty>
        <EmptyTitle>No words yet</EmptyTitle>
        <EmptyDescription>
          {canEdit
            ? "Search for a word to add it to this deck."
            : "This deck does not have any words yet."}
        </EmptyDescription>
        {canEdit ? <AddWordAction nodeId={nodeId} className="mt-2" /> : null}
      </Empty>
    )
  }

  function confirmRemoval(sense: SenseContent) {
    const senseId = sense.senseId
    if (senseId == null) return

    startRemoving(async () => {
      const result = await removeSenseFromDeck(nodeId, senseId)
      setPending(null)

      if (!result.success) {
        toastApiError(result, "Could not remove the word")
        return
      }

      // The removal invalidated the session, so the study screen's copy of it is
      // already dead. Only a session this deck actually covers is cleared: one on
      // an unrelated deck is untouched by this change and must survive.
      if (affectedSession) setLiveSession(null)
      toast.add({ title: "Word removed" })
    })
  }

  return (
    <>
      <ul className="flex flex-col divide-y divide-border border-y border-border">
        {items.map((sense) => (
          <DeckItemRow
            key={sense.senseId ?? sense.definition}
            item={sense}
            asOf={asOf}
            action={
              canEdit ? (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => setPending(sense)}
                  aria-label={`Remove ${sense.word ?? "this word"} from this deck`}
                >
                  <MinusIcon />
                </Button>
              ) : undefined
            }
          />
        ))}
      </ul>

      {pending ? (
        <RemoveWordDialog
          sense={pending}
          affectedSession={affectedSession}
          isRemoving={isRemoving}
          onConfirm={() => confirmRemoval(pending)}
          onCancel={() => setPending(null)}
        />
      ) : null}
    </>
  )
}

/**
 * The removal confirmation.
 *
 * Two consequences, and both are stated rather than implied: the learning history
 * for this word in this deck goes, and a session in progress on this deck ends. The
 * second line appears only when a session is actually live.
 */
function RemoveWordDialog({
  sense,
  affectedSession,
  isRemoving,
  onConfirm,
  onCancel,
}: {
  sense: SenseContent
  /** Non-null only when a live session actually covers this deck. */
  affectedSession: LiveSession | null
  isRemoving: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const label = sense.word ?? "this word"

  return (
    <AlertDialog
      open
      onOpenChange={(next) => {
        if (!next) onCancel()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia>
            <WarningIcon className="text-on-wash-warn" />
          </AlertDialogMedia>
          <AlertDialogTitle>Remove {label} from this deck?</AlertDialogTitle>
          <AlertDialogDescription>
            Your review history for {label} in this deck is deleted and cannot be
            restored. The word itself stays in the dictionary.
            {affectedSession
              ? " You are studying this deck, so the session ends as well."
              : ""}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm} disabled={isRemoving}>
            Remove
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
