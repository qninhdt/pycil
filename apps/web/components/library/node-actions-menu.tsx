"use client"

import { useState } from "react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  ArrowsOutCardinalIcon,
  DotsThreeIcon,
  GlobeIcon,
  LockIcon,
  PencilSimpleIcon,
  TrashIcon,
} from "@/lib/icons"
import type { NodeRead } from "@/lib/api/types"

import { DeleteNodeDialog } from "./delete-node-dialog"
import { MoveNodeDialog } from "./move-node-dialog"
import { RenameNodeDialog } from "./rename-node-dialog"
import { VisibilityDialog } from "./visibility-dialog"

/** Which dialog is open. One at a time, so this is a single value. */
type OpenDialog = "none" | "rename" | "move" | "visibility" | "delete"

/**
 * Every mutation available on a node, behind one menu.
 *
 * Rendered only for a node the viewer owns. An anonymous reader and a signed-in
 * reader of someone else's public deck get no menu at all rather than a menu of
 * disabled items: the API refuses each of these with `forbidden`, so offering them
 * would be advertising a failure.
 *
 * The dialogs are mounted here rather than at each call site so a row and a header
 * share one implementation of each mutation.
 */
export function NodeActionsMenu({ node }: { node: NodeRead }) {
  const [dialog, setDialog] = useState<OpenDialog>("none")
  const close = () => setDialog("none")

  const isPublic = node.visibility === "PUBLIC"

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button variant="ghost" size="icon-sm" aria-label={`Actions for ${node.name}`}>
              <DotsThreeIcon />
            </Button>
          }
        />
        <DropdownMenuContent align="end">
          <DropdownMenuGroup>
            <DropdownMenuItem onClick={() => setDialog("rename")}>
              <PencilSimpleIcon data-icon="inline-start" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setDialog("move")}>
              <ArrowsOutCardinalIcon data-icon="inline-start" />
              Move
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setDialog("visibility")}>
              {isPublic ? (
                <LockIcon data-icon="inline-start" />
              ) : (
                <GlobeIcon data-icon="inline-start" />
              )}
              {isPublic ? "Make private" : "Share by link"}
            </DropdownMenuItem>
          </DropdownMenuGroup>
          <DropdownMenuSeparator />
          <DropdownMenuGroup>
            <DropdownMenuItem variant="destructive" onClick={() => setDialog("delete")}>
              <TrashIcon data-icon="inline-start" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Each dialog is mounted only while open, so a closed one holds no state to
          go stale against a node that changed underneath it. */}
      {dialog === "rename" ? (
        <RenameNodeDialog node={node} open onClose={close} />
      ) : null}
      {dialog === "move" ? <MoveNodeDialog node={node} open onClose={close} /> : null}
      {dialog === "visibility" ? (
        <VisibilityDialog node={node} open onClose={close} />
      ) : null}
      {dialog === "delete" ? (
        <DeleteNodeDialog node={node} open onClose={close} />
      ) : null}
    </>
  )
}
