"use client"

import { useState, useTransition } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldLabel } from "@/components/ui/field"
import { toast } from "@/components/ui/toast"
import { updateNodeVisibility } from "@/lib/actions/nodes"
import { classifyErrorCode } from "@/lib/api/error-taxonomy"
import type { NodeRead } from "@/lib/api/types"
import { GlobeIcon, LockIcon, WarningIcon } from "@/lib/icons"

import { nodeTypeLabel } from "./node-icon"

/**
 * Publishing and unpublishing a node.
 *
 * Publishing a folder publishes everything beneath it, which is why the API refuses
 * a folder publication without `confirmSubtreePublication` and answers
 * `folder_publication_requires_confirmation`. That refusal is a prompt, not a
 * failure — but the confirmation is collected here, before the first call, so the
 * learner is told what the scope is rather than being asked to re-confirm something
 * they were never warned about.
 *
 * A public item is reachable by anyone holding the link and does not appear in
 * anyone else's listings. The copy says exactly that, because "public" alone
 * invites the assumption that it is indexed somewhere.
 */
export function VisibilityDialog({
  node,
  open,
  onClose,
}: {
  node: NodeRead
  open: boolean
  onClose: () => void
}) {
  const publishing = node.visibility === "PRIVATE"
  const isFolder = node.type === "FOLDER"
  const needsSubtreeAck = publishing && isFolder

  const [acknowledged, setAcknowledged] = useState(false)
  const [isSaving, startSaving] = useTransition()

  const canSave = !needsSubtreeAck || acknowledged

  function submit() {
    if (!canSave) return

    startSaving(async () => {
      const result = await updateNodeVisibility(node.id, {
        visibility: publishing ? "PUBLIC" : "PRIVATE",
        // Sent only for the case that requires it. Passing it unconditionally
        // would mean a deck publication carries an acknowledgement the learner
        // was never shown.
        ...(needsSubtreeAck ? { confirmSubtreePublication: true } : {}),
      })

      if (!result.success) {
        toast.add({
          title: "Could not change visibility",
          description: classifyErrorCode(result.code).message,
        })
        return
      }

      setAcknowledged(false)
      onClose()
      toast.add({
        title: publishing ? "Now shared by link" : "Now private",
      })
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setAcknowledged(false)
          onClose()
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {publishing ? "Share" : "Make private"} {node.name}
          </DialogTitle>
          <DialogDescription>
            {publishing
              ? `Anyone with the link can read this ${nodeTypeLabel(node.type).toLowerCase()}. It does not appear in anyone else's library, and no one can change it.`
              : "Only you will be able to open it. Existing links stop working."}
          </DialogDescription>
        </DialogHeader>

        {needsSubtreeAck ? (
          <Alert>
            <WarningIcon />
            <AlertTitle>Everything inside becomes readable too</AlertTitle>
            <AlertDescription>
              Sharing this folder shares every folder and deck inside it, including
              ones you add later. Each word list beneath it becomes readable by
              anyone holding the link.
            </AlertDescription>
          </Alert>
        ) : null}

        {needsSubtreeAck ? (
          <Field orientation="horizontal">
            <Checkbox
              id="confirm-subtree-publication"
              checked={acknowledged}
              onCheckedChange={(checked) => setAcknowledged(checked === true)}
            />
            <FieldLabel htmlFor="confirm-subtree-publication">
              I understand the whole folder becomes readable.
            </FieldLabel>
          </Field>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSave || isSaving}>
            {publishing ? (
              <>
                <GlobeIcon data-icon="inline-start" />
                Share by link
              </>
            ) : (
              <>
                <LockIcon data-icon="inline-start" />
                Make private
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
