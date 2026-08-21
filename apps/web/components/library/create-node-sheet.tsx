"use client"

import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { Textarea } from "@/components/ui/textarea"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { toast } from "@/components/ui/toast"
import { createNode } from "@/lib/actions/nodes"
import type { NodeType } from "@/lib/api/types"
import { toastApiError } from "@/lib/feedback/toast-api-error"
import { PlusIcon } from "@/lib/icons"

import { nodeTypeLabel } from "./node-icon"

/**
 * Creating a folder, a deck, or a reference.
 *
 * One sheet for all three because they differ by a single field: a reference needs
 * a target deck, and the other two do not. Three separate dialogs would triple the
 * form for one conditional input.
 *
 * A reference is created here without a target picker: the API requires
 * `targetNodeId` and answers `reference_requires_target` without it, so the
 * reference option is offered only when a target is supplied by the caller. That
 * keeps this form from presenting a choice that cannot succeed.
 */
export function CreateNodeSheet({
  parentNodeId,
  targetNodeId,
  trigger,
}: {
  /** Null creates at the root. */
  parentNodeId: string | null
  /** Present only when the caller is creating a reference to a known deck. */
  targetNodeId?: string
  /**
   * A custom trigger, passed to the primitive's `render` so it keeps real button
   * semantics. It must be a single focusable element — a click handler on a
   * wrapper would open the sheet for a pointer and leave it unreachable by
   * keyboard.
   */
  trigger?: React.ReactElement
}) {
  const [open, setOpen] = useState(false)
  const [type, setType] = useState<NodeType>(targetNodeId ? "REFERENCE" : "DECK")
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [isSaving, startSaving] = useTransition()

  const trimmedName = name.trim()

  function submit() {
    if (trimmedName.length === 0) return

    startSaving(async () => {
      const result = await createNode({
        type,
        name: trimmedName,
        parentNodeId,
        description: description.trim() || null,
        targetNodeId: type === "REFERENCE" ? targetNodeId : null,
      })

      if (!result.success) {
        toastApiError(result, "Could not create it")
        return
      }

      setName("")
      setDescription("")
      setOpen(false)
      toast.add({ title: `${nodeTypeLabel(type)} created` })
    })
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      {/* The trigger lives inside `Sheet` so the primitive owns opening, focus,
          and returning focus on close. A custom trigger is passed through
          `render` rather than wrapped in a click handler: a wrapper element
          gets no focus, no Enter or Space activation, and no button role, so
          the control would work with a mouse and be unreachable otherwise. */}
      <SheetTrigger
        render={
          trigger ?? (
            <Button size="sm">
              <PlusIcon data-icon="inline-start" />
              New
            </Button>
          )
        }
      />

      <SheetContent side="bottom" className="lg:max-w-md">
        <SheetHeader>
          <SheetTitle>Create something new</SheetTitle>
          <SheetDescription>
            A deck holds words. A folder holds decks and other folders.
          </SheetDescription>
        </SheetHeader>

        <FieldGroup className="px-4">
          <Field>
            <FieldLabel>Kind</FieldLabel>
            <ToggleGroup
              value={[type]}
              onValueChange={(value) => {
                const next = value[0]
                if (next) setType(next as NodeType)
              }}
            >
              <ToggleGroupItem value="DECK">Deck</ToggleGroupItem>
              <ToggleGroupItem value="FOLDER">Folder</ToggleGroupItem>
              {targetNodeId ? (
                <ToggleGroupItem value="REFERENCE">Reference</ToggleGroupItem>
              ) : null}
            </ToggleGroup>
          </Field>

          <Field>
            <FieldLabel htmlFor="new-node-name">Name</FieldLabel>
            <Input
              id="new-node-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder={type === "FOLDER" ? "Phrasal verbs" : "Week 1"}
              autoFocus
            />
          </Field>

          <Field>
            <FieldLabel htmlFor="new-node-description">Description</FieldLabel>
            <Textarea
              id="new-node-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              rows={2}
            />
            <FieldDescription>Optional.</FieldDescription>
          </Field>
        </FieldGroup>

        <SheetFooter>
          <Button
            onClick={submit}
            disabled={trimmedName.length === 0 || isSaving}
          >
            Create
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}
