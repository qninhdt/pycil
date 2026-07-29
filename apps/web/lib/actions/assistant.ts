"use server"

import type { ActionResult } from "@/lib/api/handle-api-error"
import type { RunEvent, RunRecovery, Thread } from "@/lib/api/types"

import { withClient } from "./authorized-action"

/**
 * Thread management and run recovery.
 *
 * Sending a message and confirming an action are absent on purpose: both answer
 * with `text/event-stream`, and a server action cannot return a stream. They stay
 * as route handlers under `app/api/assistant/**`, which is the one case a handler
 * still earns its place.
 */

export async function listThreads(): Promise<ActionResult<Thread[]>> {
  return withClient((client) => client.assistant.listThreads())
}

export async function createThread(title?: string): Promise<ActionResult<Thread>> {
  const trimmed = title?.trim()
  return withClient((client) =>
    client.assistant.createThread(trimmed ? { title: trimmed } : {}),
  )
}

export async function deleteThread(threadId: string): Promise<ActionResult<void>> {
  return withClient((client) => client.assistant.deleteThread(threadId))
}

/** The persisted transcript, for a thread opened fresh rather than resumed. */
export async function getThreadMessages(
  threadId: string,
): Promise<ActionResult<RunEvent[]>> {
  return withClient((client) => client.assistant.getThreadMessages(threadId))
}

/**
 * Replays a run from its event cursor after a dropped stream.
 *
 * The stream is not resumable, so recovery means reading the run's persisted
 * events and continuing from the cursor rather than reconnecting to the original
 * response.
 */
export async function recoverRun(
  threadId: string,
  runId: string,
): Promise<ActionResult<RunRecovery>> {
  return withClient((client) => client.assistant.getRun(threadId, runId))
}
