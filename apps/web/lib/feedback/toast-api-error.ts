"use client"

import { toast } from "@/components/ui/toast"
import { classifyErrorCode } from "@/lib/api/error-taxonomy"

/** The failure half of an `ActionResult`, as a caller sees it after narrowing. */
interface FailedAction {
  success: false
  code: string
}

/**
 * Reports a failed action result as a toast.
 *
 * One mapping from wire error code to learner-facing words, so every surface
 * phrases a failure the same way instead of growing its own taxonomy copy.
 * With a title the message becomes the description ("Could not move it" over
 * "A folder cannot be moved inside itself."); without one the message stands
 * alone, for surfaces that have nothing useful to add above it.
 */
export function toastApiError(result: FailedAction, title?: string): void {
  const message = classifyErrorCode(result.code).message
  toast.add(title ? { title, description: message } : { title: message })
}
