"use client"

import { useRouter } from "next/navigation"
import { useTransition } from "react"

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
import { toast } from "@/components/ui/toast"
import { deleteNode } from "@/lib/actions/nodes"
import { classifyErrorCode } from "@/lib/api/error-taxonomy"
import type { NodeRead } from "@/lib/api/types"
import { WarningIcon } from "@/lib/icons"

import { nodeTypeLabel } from "./node-icon"

/**
 * Deleting a node.
 *
 * An `AlertDialog` rather than a `Dialog`: this is destructive and the primitive
 * that traps focus on the confirming action is the right one for it.
 *
 * A folder takes its whole subtree with it, and the copy says so. For a deck, what
 * is lost is the word list and its review history — the words themselves are
 * dictionary content and survive. Both consequences are stated because "are you
 * sure" tells the learner nothing they did not already know.
 */
export function DeleteNodeDialog({
  node,
  open,
  onClose,
}: {
  node: NodeRead
  open: boolean
  onClose: () => void
}) {
  const router = useRouter()
  const [isDeleting, startDeleting] = useTransition()

  const kind = nodeTypeLabel(node.type).toLowerCase()

  function submit() {
    startDeleting(async () => {
      const result = await deleteNode(node.id)

      if (!result.success) {
        toast.add({
          title: `Could not delete this ${kind}`,
          description: classifyErrorCode(result.code).message,
        })
        return
      }

      onClose()
      toast.add({ title: `${node.name} deleted` })
      // The page being viewed is the thing that was just deleted, so staying put
      // would render a 404 on the next read. The parent is where the learner was
      // before opening it.
      router.push(node.parentNodeId ? `/library/${node.parentNodeId}` : "/library")
    })
  }

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogMedia>
            <WarningIcon className="text-destructive" />
          </AlertDialogMedia>
          <AlertDialogTitle>Delete {node.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            {node.type === "FOLDER"
              ? "Every folder and deck inside this one is deleted with it, along with the review history for each word list. This cannot be undone."
              : node.type === "REFERENCE"
                ? "This link is removed. The deck it points at is left alone."
                : "The word list and your review history for it are deleted. This cannot be undone. The words themselves stay in the dictionary."}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Keep it</AlertDialogCancel>
          <AlertDialogAction onClick={submit} disabled={isDeleting}>
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
