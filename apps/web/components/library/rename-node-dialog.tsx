"use client"

import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { toast } from "@/components/ui/toast"
import { updateNode } from "@/lib/actions/nodes"
import type { NodeRead } from "@/lib/api/types"
import { toastApiError } from "@/lib/feedback/toast-api-error"

/**
 * Renaming a node and editing its description.
 *
 * Both live in one dialog because the API accepts them in one PATCH, and a learner
 * fixing a deck name usually wants to fix its description in the same visit.
 *
 * The form is seeded from the node and submits only what changed: sending an
 * unchanged description would still bump the node's `updatedAt`, which is what the
 * library sorts and displays.
 */
export function RenameNodeDialog({
  node,
  open,
  onClose,
}: {
  node: NodeRead
  open: boolean
  onClose: () => void
}) {
  const [name, setName] = useState(node.name)
  const [description, setDescription] = useState(node.description ?? "")
  const [isSaving, startSaving] = useTransition()

  const trimmedName = name.trim()
  const trimmedDescription = description.trim()
  const nameChanged = trimmedName !== node.name
  const descriptionChanged = trimmedDescription !== (node.description ?? "")
  const canSave = trimmedName.length > 0 && (nameChanged || descriptionChanged)

  function submit() {
    if (!canSave) return

    startSaving(async () => {
      const result = await updateNode(node.id, {
        ...(nameChanged ? { name: trimmedName } : {}),
        ...(descriptionChanged ? { description: trimmedDescription || null } : {}),
      })

      if (!result.success) {
        toastApiError(result, "Could not save the change")
        return
      }

      onClose()
      toast.add({ title: "Saved" })
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Edit {node.name}</DialogTitle>
          <DialogDescription>
            The name is what you see in your library. The description is for you.
          </DialogDescription>
        </DialogHeader>

        <FieldGroup>
          <Field>
            <FieldLabel htmlFor="rename-node-name">Name</FieldLabel>
            <Input
              id="rename-node-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              autoFocus
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="rename-node-description">Description</FieldLabel>
            <Textarea
              id="rename-node-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={2}
            />
            <FieldDescription>Optional.</FieldDescription>
          </Field>
        </FieldGroup>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSave || isSaving}>
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
