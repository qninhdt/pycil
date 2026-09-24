"use client"

/**
 * The learner's conversations, with create and delete.
 *
 * Threads are a list rather than a single implicit conversation because the
 * assistant acts on the library: "tidy my French decks" and "add these ten words"
 * are separate pieces of work, and merging them into one endless thread makes the
 * model's context the sum of every request ever made.
 */

import { useState, useTransition } from "react"

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
import { Button } from "@/components/ui/button"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import { Spinner } from "@/components/ui/spinner"
import { toast } from "@/components/ui/toast"
import { createThread, deleteThread } from "@/lib/actions/assistant"
import type { Thread } from "@/lib/api/types"
import { toastApiError } from "@/lib/feedback/toast-api-error"
import { ChatCircleIcon, PlusIcon, TrashIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

export function ThreadList({
  threads,
  activeThreadId,
  onOpen,
  onChanged,
}: {
  threads: Thread[]
  activeThreadId: string | null
  onOpen: (threadId: string) => void
  /** Refetches the list after a create or delete, which the parent owns. */
  onChanged: () => void
}) {
  const [pendingDelete, setPendingDelete] = useState<Thread | null>(null)
  const [isMutating, startMutating] = useTransition()

  function create() {
    startMutating(async () => {
      const result = await createThread()
      if (!result.success) {
        toastApiError(result)
        return
      }
      onChanged()
      // Opened straight away: creating a conversation is only ever a prelude to
      // having one, so making the learner then click it is a step for nothing.
      onOpen(result.data.id)
    })
  }

  function confirmDelete(thread: Thread) {
    startMutating(async () => {
      const result = await deleteThread(thread.id)
      setPendingDelete(null)
      if (!result.success) {
        toastApiError(result)
        return
      }
      onChanged()
      toast.add({ title: "Conversation deleted" })
    })
  }

  return (
    <div className="flex min-h-0 flex-col gap-2">
      <Button
        variant="outline"
        size="sm"
        onClick={create}
        disabled={isMutating}
        className="justify-start"
      >
        {isMutating ? <Spinner /> : <PlusIcon data-icon="inline-start" />}
        New conversation
      </Button>

      {threads.length === 0 ? (
        <Empty className="border-none py-6">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <ChatCircleIcon />
            </EmptyMedia>
            <EmptyTitle>No conversations yet</EmptyTitle>
            {/* What it can do, not "no threads". A blank assistant with no stated
                capability is a text box the learner has no reason to type into. */}
            <EmptyDescription>
              Ask for words to be added, decks to be organised, or a folder to be
              summarised. Anything that deletes or publishes asks you first.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <ul className="flex min-h-0 flex-col overflow-y-auto">
          {threads.map((thread) => (
            <li key={thread.id} className="flex items-center gap-1">
              <button
                type="button"
                data-thread-id={thread.id}
                onClick={() => onOpen(thread.id)}
                aria-current={thread.id === activeThreadId ? "true" : undefined}
                className={cn(
                  "min-h-11 flex-1 truncate rounded-md px-2 text-left text-sm outline-none",
                  "hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring",
                  thread.id === activeThreadId && "bg-muted font-medium",
                )}
              >
                {thread.title}
              </button>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Delete ${thread.title}`}
                onClick={() => setPendingDelete(thread)}
              >
                <TrashIcon />
              </Button>
            </li>
          ))}
        </ul>
      )}

      {/* Deletion is destructive and irreversible — the API removes the thread and
          its events — so it is confirmed rather than undone. */}
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              {pendingDelete?.title} and its messages are removed for good. Words and
              decks the assistant already changed stay as they are.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep it</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => pendingDelete && confirmDelete(pendingDelete)}
              disabled={isMutating}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}
