"use client"

import { useEffect, useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { listMoveDestinations, moveNode } from "@/lib/actions/nodes"
import type { NodeRead } from "@/lib/api/types"
import { toastApiError } from "@/lib/feedback/toast-api-error"
import { CaretRightIcon, FolderIcon, HouseIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

/**
 * Choosing a new parent for a node.
 *
 * The picker walks one level at a time rather than rendering the whole tree. The
 * API pages children by parent, so a full tree would mean fetching every node the
 * learner owns to populate a list they will click twice.
 *
 * Only folders are offered, and the node itself is never offered as its own
 * destination. Its descendants are a harder case: the API rejects a cycle with
 * `node_move_would_create_cycle`, and the picker cannot know the full subtree
 * without walking it, so that refusal is surfaced as an error rather than
 * pre-empted. Trying is cheap and the message is specific.
 */
export function MoveNodeDialog({
  node,
  open,
  onClose,
}: {
  node: NodeRead
  open: boolean
  onClose: () => void
}) {
  const [browsingId, setBrowsingId] = useState<string | null>(null)
  const [trail, setTrail] = useState<NodeRead[]>([])
  const [isSaving, startSaving] = useTransition()

  // One piece of state holding the folders *and* the level they belong to. Keeping
  // both together is what lets "still loading" be derived below rather than set, so
  // the effect never writes state synchronously — which would cascade a second
  // render on every level change. It also discards a stale response by
  // construction: folders are only shown when they answer the level on screen now.
  const [settled, setSettled] = useState<{
    browsingId: string | null
    folders: NodeRead[]
  } | null>(null)

  useEffect(() => {
    if (!open) return

    let current = true

    listMoveDestinations(browsingId).then((result) => {
      if (!current) return
      if (!result.success) {
        toastApiError(result, "Could not load folders")
        // Recorded as an empty level rather than left pending, so the surface stops
        // claiming to load something that already came back.
        setSettled({ browsingId, folders: [] })
        return
      }
      // The node cannot be moved inside itself, so it is never a destination.
      setSettled({
        browsingId,
        folders: result.data.filter((folder) => folder.id !== node.id),
      })
    })

    return () => {
      current = false
    }
  }, [open, browsingId, node.id])

  const isLoading = settled === null || settled.browsingId !== browsingId
  const folders = isLoading ? [] : settled.folders

  function reset() {
    setBrowsingId(null)
    setTrail([])
  }

  function submit() {
    startSaving(async () => {
      const result = await moveNode(node.id, browsingId)

      if (!result.success) {
        toastApiError(result, "Could not move it")
        return
      }

      reset()
      onClose()
      toast.add({ title: `${node.name} moved` })
    })
  }

  const destinationName = trail.at(-1)?.name ?? "your library"

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
          onClose()
        }
      }}
    >
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Move {node.name}</DialogTitle>
          <DialogDescription>
            Open a folder to look inside it, then move this here.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 px-4">
          <nav aria-label="Destination" className="flex flex-wrap items-center gap-1">
            <button
              type="button"
              onClick={reset}
              className={cn(
                "flex min-h-8 items-center gap-1.5 rounded-md px-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                browsingId === null
                  ? "font-medium text-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <HouseIcon />
              Library
            </button>
            {trail.map((step, index) => (
              <span key={step.id} className="flex items-center gap-1">
                <CaretRightIcon className="size-3 text-muted-foreground" />
                <button
                  type="button"
                  onClick={() => {
                    setBrowsingId(step.id)
                    setTrail(trail.slice(0, index + 1))
                  }}
                  className={cn(
                    "min-h-8 rounded-md px-1.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    index === trail.length - 1
                      ? "font-medium text-foreground"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {step.name}
                </button>
              </span>
            ))}
          </nav>

          <div className="min-h-32 border-y border-border">
            {isLoading ? (
              <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
                <Spinner className="size-4" />
                Loading
              </div>
            ) : folders.length === 0 ? (
              <p className="py-6 text-sm text-muted-foreground">
                No folders in here. You can still move it to this level.
              </p>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {folders.map((folder) => (
                  <li key={folder.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setBrowsingId(folder.id)
                        setTrail([...trail, folder])
                      }}
                      className="flex min-h-11 w-full items-center gap-3 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                    >
                      <FolderIcon className="shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-sm">
                        {folder.name}
                      </span>
                      <CaretRightIcon className="shrink-0 text-muted-foreground" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={isSaving}>
            Move to {destinationName}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
