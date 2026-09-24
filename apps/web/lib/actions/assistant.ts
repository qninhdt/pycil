import type { ActionResult } from "@/lib/api/handle-api-error"
import type { ThreadState } from "@/lib/api/resources/assistant"
import type { ModelCatalog, Thread } from "@/lib/api/types"

import { withClient } from "./authorized-action"

export async function listThreads(): Promise<ActionResult<Thread[]>> {
  return withClient((client) => client.assistant.listThreads())
}

export async function createThread(title?: string): Promise<ActionResult<Thread>> {
  const trimmed = title?.trim()
  return withClient((client) => client.assistant.createThread(trimmed ? { title: trimmed } : {}))
}

export async function deleteThread(threadId: string): Promise<ActionResult<void>> {
  return withClient((client) => client.assistant.deleteThread(threadId))
}

export async function getThreadState(threadId: string): Promise<ActionResult<ThreadState>> {
  return withClient((client) => client.assistant.getThreadState(threadId))
}

/** The server's model allowlist. The UI offers only what this returns. */
export async function getModelCatalog(): Promise<ActionResult<ModelCatalog>> {
  return withClient((client) => client.assistant.getModels())
}
