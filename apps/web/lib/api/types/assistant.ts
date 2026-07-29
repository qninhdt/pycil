/**
 * Assistant threads, runs, and the SSE event stream.
 *
 * Event names are taken from the `append_event` call sites rather than from the
 * OpenAPI document, which types every payload as an open object. The previous
 * hand-authored union declared an `"action"` event that the API has never
 * emitted; the real name is `confirmation_required`.
 */

export type RunStatus =
  | "pending"
  | "running"
  | "interrupted"
  | "succeeded"
  | "failed"
  | "cancelled"

export interface Thread {
  id: string
  title: string
  status: string
  createdAt: string | null
  updatedAt: string | null
}

export interface ThreadCreate {
  title?: string
}

export interface MessageCreate {
  /** Client-minted, and rejected on reuse with `client_message_id_reused`. */
  clientMessageId: string
  content: string
}

/**
 * What kind of run event arrived.
 *
 * `token` streams assistant text. `tool_call` and `tool_result` narrate work.
 * `confirmation_required` is the human-in-the-loop pause: the run stops until the
 * action is approved or rejected. `done` and `error` are terminal.
 */
export type RunEventType =
  | "user_message"
  | "token"
  | "tool_call"
  | "tool_result"
  | "confirmation_required"
  | "done"
  | "error"

/**
 * The payload per event type, as written by the API.
 *
 * Every payload is an object, `token` included: `append_event` is typed
 * `payload: dict` and `_token_payload` (`assistant/run_service.py:131`) wraps the
 * chunk as `{"content": ...}`. An earlier revision of this file typed `token` as a
 * bare string, which type-checked clean and would have rendered every streamed
 * token as `undefined`.
 */
export interface RunEventPayloads {
  user_message: { content: string }
  token: { content: string }
  tool_call: { tool: string }
  tool_result: { tool: string; content: string }
  confirmation_required: {
    action_id: string
    tool: string
    expires_at: string
    /**
     * The names of the nodes the tool would act on, keyed by argument name.
     *
     * Present so an approval prompt can say *what* is about to be deleted rather
     * than only which function would run. Keys are the tool's own argument names
     * (`node_id`, `deck_id`, `parent_id`), and only owned, resolvable targets
     * appear — so this can be empty, and a card must still be honest when it is.
     */
    targets: Record<string, string>
  }
  done: Record<string, never>
  error: { code: "deadline_exceeded" | "execution_failed" | string }
}

export type RunEvent = {
  [K in RunEventType]: {
    id: string
    /**
     * Which run this event belongs to.
     *
     * Load-bearing, because `sequence` is per-run: it counts `run.event_cursor`
     * (`assistant/run_service.py:108`), while `GET .../messages` returns every run
     * in the thread. So the second turn's first event is also sequence 1, and
     * anything keyed on sequence alone collapses one turn onto another.
     *
     * A replayed event carries the real run id. A *streamed* frame does not — the
     * wire format is `id: <sequence>` with no run — so the hook supplies the turn's
     * `clientMessageId` instead, which identifies the same run by its idempotency
     * key. Either way the value is stable for one run and unique across runs, which
     * is all a key needs to be.
     */
    runId: string
    sequence: number
    eventType: K
    payload: RunEventPayloads[K]
  }
}[RunEventType]

/** Replayed state after a dropped stream, from the event cursor onwards. */
export interface RunRecovery {
  id: string
  threadId: string
  status: RunStatus
  eventCursor: number
  events: RunEvent[]
  errorCode?: string | null
}

// The SSE frame has no type here on purpose. Its shape — `id`, `event`, `data` — is
// a transport detail of the byte stream, and `lib/assistant/sse-frames.ts` models it
// as `ParsedFrame` at the one place that parses it. A second declaration in the wire
// contract would be a shape nothing validates against and nothing imports.

export type ActionDecision = "approve" | "reject"

// `AccountExport` lives in ./auth: `/v1/me/export` is an account endpoint, and
// the assistant section of it is one opaque member among five.
