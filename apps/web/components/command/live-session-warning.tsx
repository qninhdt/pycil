"use client"

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
import { WarningIcon } from "@/lib/icons"
import type { LiveSession } from "@/lib/stores/ui-store"

/**
 * Confirms an add that will end the session the learner is in the middle of.
 *
 * This is not a courtesy. Adding a sense bumps the deck's structural generation
 * and that of every ancestor and reverse reference, and the API compares the
 * session's recorded generation on both `next` and `answers` — so the add ends
 * the session, and an answer already on screen is discarded rather than graded.
 *
 * The wording says the session ends, not that "something may change", because
 * ending it is exactly what happens.
 */
export function LiveSessionWarning({
  liveSession,
  open,
  onConfirm,
  onCancel,
}: {
  liveSession: LiveSession
  open: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onCancel()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia>
            <WarningIcon className="text-on-wash-warn" />
          </AlertDialogMedia>
          <AlertDialogTitle>End your session to add this word?</AlertDialogTitle>
          <AlertDialogDescription>
            You are studying {liveSession.deckTitle}. Adding a word changes what
            the session covers, so the session ends and any answer on screen is
            not counted. Your finished answers are already saved.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep studying</AlertDialogCancel>
          <AlertDialogAction onClick={onConfirm}>
            Add and end session
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
