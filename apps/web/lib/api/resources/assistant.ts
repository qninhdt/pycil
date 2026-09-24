import type { Fetcher } from "../request"
import type { ModelCatalog, Thread, ThreadCreate } from "../types"

export interface ThreadState {
  status: string
  messages: Array<Record<string, unknown>>
  interrupts: Array<Record<string, unknown>>
}

export function assistantResource(fetch: Fetcher) {
  return {
    listThreads: () => fetch<Thread[]>("/v1/assistant/threads"),
    createThread: (body: ThreadCreate = {}) =>
      fetch<Thread>("/v1/assistant/threads", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    deleteThread: (threadId: string) =>
      fetch<void>(`/v1/assistant/threads/${threadId}`, { method: "DELETE" }),
    getThreadState: (threadId: string) =>
      fetch<ThreadState>(`/v1/assistant/threads/${threadId}/state`),
    /** The allowlist a model selector may offer. Never hard-coded in the UI. */
    getModels: () => fetch<ModelCatalog>("/v1/assistant/models"),
  }
}
