import Link from "next/link"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"

/**
 * Leaving a session part-way.
 *
 * The copy states that finished work is kept, because it is: a verdict is applied
 * durably per answer, so the FSRS consequence of every graded answer is already
 * committed before this dialog can open. Warning a learner that they will "lose
 * progress" would be false, and the fear costs them the session they were going to
 * come back to.
 *
 * What is genuinely lost is the rest of the plan — the words admitted but not yet
 * finished stay unfinished, and they come back in a later session rather than
 * disappearing.
 */
export function ExitSessionDialog({
  open,
  onOpenChange,
  /** The deck to return to, or null when the session's node is unknown. */
  nodeId,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  nodeId: string | null
}) {
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Leave this session?</AlertDialogTitle>
          <AlertDialogDescription>
            Every answer you have already had marked is saved. The words you have not
            reached yet stay unfinished and come back in a later session.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep studying</AlertDialogCancel>
          {/* A link rather than a router push: leaving is a navigation, and rendering
              it as an anchor keeps middle-click and the browser's own history
              behaviour working. */}
          <AlertDialogAction
            render={<Link href={nodeId ? `/library/${nodeId}` : "/library"} />}
          >
            Leave
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
