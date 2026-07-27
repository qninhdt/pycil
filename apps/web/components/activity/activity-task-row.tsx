"use client"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import type { ActivityTask } from "@/lib/stores/activity-store"
import {
  CheckCircleIcon,
  HourglassIcon,
  WarningCircleIcon,
  XIcon,
} from "@/lib/icons"

/** What each kind of work is called in the list. */
const KIND_LABEL: Record<ActivityTask["kind"], string> = {
  "word-generation": "Adding a word",
  "question-generation": "Preparing questions",
  grade: "Marking an answer",
}

/**
 * A settled task states its outcome; an unsettled one states that it is still
 * running. "unknown" is the status of a task restored from a reload before its
 * first snapshot arrives, and it reads as pending because that is what it is.
 */
function describe(task: ActivityTask): {
  text: string
  tone: "pending" | "done" | "failed"
} {
  switch (task.status) {
    case "succeeded":
      return { text: "Done", tone: "done" }
    case "failed":
      return {
        // The error code is the API's, so it is shown rather than mapped to a
        // guess: an unmapped code would otherwise read as a generic failure.
        text: task.errorCode ? `Failed (${task.errorCode})` : "Failed",
        tone: "failed",
      }
    case "expired":
      return { text: "Expired", tone: "failed" }
    case "queued":
      return { text: "Queued", tone: "pending" }
    default:
      return { text: "Working", tone: "pending" }
  }
}

export function ActivityTaskRow({
  task,
  onDismiss,
}: {
  task: ActivityTask
  onDismiss: (taskId: string) => void
}) {
  const { text, tone } = describe(task)

  return (
    <li className="flex items-start gap-3 py-3">
      <span className="mt-0.5 shrink-0">
        {tone === "pending" ? (
          <Spinner className="size-4 text-muted-foreground" />
        ) : tone === "done" ? (
          <CheckCircleIcon className="size-4 text-on-wash-success" />
        ) : (
          <WarningCircleIcon className="size-4 text-destructive" />
        )}
      </span>

      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm">
          {KIND_LABEL[task.kind]}
          {task.label ? (
            <span className="font-serif text-muted-foreground"> · {task.label}</span>
          ) : null}
        </span>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          {text}
          {task.stale ? (
            <Badge variant="outline">
              <HourglassIcon />
              No longer watching
            </Badge>
          ) : null}
        </span>
      </span>

      <Button
        variant="ghost"
        size="icon-sm"
        aria-label={`Dismiss ${KIND_LABEL[task.kind].toLowerCase()}`}
        onClick={() => onDismiss(task.taskId)}
      >
        <XIcon />
      </Button>
    </li>
  )
}
