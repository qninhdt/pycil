import type { Fetcher } from "../request"
import type { RunEvent, RunRecovery, Thread, ThreadCreate } from "../types"

/**
 * Assistant threads and run recovery.
 *
 * The two streaming calls are absent on purpose. Sending a message and confirming
 * an action both return `text/event-stream`, which a JSON fetcher cannot model, so
 * they stay as route handlers under `app/api/assistant/**` where the response body
 * can be piped through untouched.
 */
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

    /** The persisted transcript, for a thread opened fresh rather than resumed. */
    getThreadMessages: (threadId: string) =>
      fetch<RunEvent[]>(`/v1/assistant/threads/${threadId}/messages`),

    /**
     * Replays a run from its event cursor after a dropped stream.
     *
     * This is the recovery path: the stream is not resumable, so a client that
     * lost one reads the run's persisted events and continues from the cursor.
     */
    getRun: (threadId: string, runId: string) =>
      fetch<RunRecovery>(`/v1/assistant/threads/${threadId}/runs/${runId}`),
  }
}

// `MessageCreate` and `ActionDecision` are not re-exported here: the two streaming
// routes import them from `@/lib/api/types` like every other consumer.
