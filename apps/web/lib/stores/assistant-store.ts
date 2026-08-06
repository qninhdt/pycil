import { createStore } from "zustand/vanilla"

import type { RunEvent, Thread } from "@/lib/api/types"

/**
 * The assistant conversation, held above the two surfaces that render it.
 *
 * The drawer and the sidebar are genuinely different components — a portal cannot
 * sit in the layout flow, so neither can be the other with CSS — and they are
 * mutually exclusive by viewport. Crossing 1024px therefore *unmounts one and
 * mounts the other*, and anything either of them owned in `useState` goes with it:
 * the open thread, the transcript, the message held for "Send again". A learner who
 * rotated a tablet, opened devtools, or dragged a window wider lost the
 * conversation they were having, with no error and nothing to recover from.
 *
 * So the conversation lives here instead, and the surfaces became renderers of it.
 * The two components stay separate — that split is correct and documented where it
 * is made; it is the *state* that was in the wrong place.
 */

/** Why the composer is unavailable, when it is. */
export type RunPhase =
  | "idle"
  /** A stream is open and events are arriving. */
  | "streaming"
  /** The stream closed with no terminal event: the run was abandoned server-side. */
  | "abandoned"

/**
 * One thread's conversation state, tagged with the thread it belongs to.
 *
 * The tag is what makes this safe. Every write goes through `updateSession`, which
 * drops the write if the thread has moved on — so a `getThreadMessages` that resolves
 * after the learner switched conversations cannot pour thread A's transcript into
 * thread B. It also means a thread change needs no reset: a mismatched tag already
 * reads as empty, which is both correct and one fewer render.
 */
export interface RunSession {
  threadId: string | null
  events: RunEvent[]
  phase: RunPhase
  /** A wire error code from a failed submission, not from a failed run. */
  problem: string | null
}

export function emptyRunSession(threadId: string | null): RunSession {
  return { threadId, events: [], phase: "idle", problem: null }
}

/**
 * Work in flight, and work already done. Deliberately not render input.
 *
 * None of these are read during render, so none of them belong in reactive state:
 * an `AbortController` has no visual meaning, and re-rendering because a turn key
 * was minted would be a render for nothing. They are held in one mutable object,
 * replaced never and mutated in place, which is what lets a value survive the
 * remount that the reactive state above also has to survive.
 *
 * `loadedThreadId` and `listLoaded` exist for exactly that remount. A newly mounted
 * surface re-runs every mount effect, and without a record of what has already been
 * read it would abort the open stream and overwrite its events with the server's
 * copy mid-turn — turning the breakpoint crossing this store exists to survive into
 * a different way of losing the same conversation.
 */
export interface AssistantTransport {
  /** The open stream, so a superseding turn or a thread change can cancel it. */
  abort: AbortController | null
  /** The current turn's idempotency key. See `claimTurnKey` for the one rule. */
  turnKey: string | null
  /** The thread whose transcript has been read. Null before the first read. */
  loadedThreadId: string | null
  /** Whether the thread list has ever been read. */
  listLoaded: boolean
}

/**
 * Mints or reuses the turn's idempotency key.
 *
 * **The rule, stated once: the key is held only while its turn's outcome is
 * unknown.** The API returns the existing run's events for a repeated key rather
 * than starting a second run, which is what makes a transport retry safe — and
 * exactly what makes reuse *unsafe* the moment the outcome is known. Sending new
 * content under a spent key takes the API's "not created" branch, which replays the
 * old run and discards what was just typed: the learner's message vanishes with no
 * error and the previous reply appears in its place.
 *
 * So every release below is one reading of that single rule, and `fresh` is the
 * caller saying the outcome is already known before it even starts.
 */
export function claimTurnKey(
  transport: AssistantTransport,
  { fresh = false }: { fresh?: boolean } = {},
): string {
  if (fresh) transport.turnKey = null
  transport.turnKey ??= crypto.randomUUID()
  return transport.turnKey
}

/** The outcome is known, so the key is spent. See `claimTurnKey` for why. */
export function releaseTurnKey(transport: AssistantTransport): void {
  transport.turnKey = null
}

export interface AssistantState {
  /** The learner's conversations. Survives a remount, so reopening shows them at once. */
  threads: Thread[]
  /**
   * Whether the list has been read even once.
   *
   * Reactive, unlike `transport.listLoaded`, and they answer different questions:
   * that one is "has a read been *started*" and gates the effect, this one is "is
   * `threads` an answer or merely an empty initial value" and gates rendering. A
   * surface that cannot tell those apart treats the pre-read moment as "no threads
   * exist", which closes the open conversation for as long as that moment lasts.
   */
  listRead: boolean
  /** A wire code from a failed listing, shown alongside whatever list is held. */
  listProblem: string | null
  /** The conversation the learner has open, or null for the list alone. */
  openThreadId: string | null
  session: RunSession
  /**
   * The last thing submitted, kept so "Send again" can actually send it again. The
   * composer clears its draft on submit, so without this the offer to resend meant
   * "retype the message you just lost from memory".
   */
  lastSent: string
  /**
   * The thread whose recovery read is outstanding, or null.
   *
   * A thread id rather than a boolean, and for the same reason `RunSession` carries
   * one: this store deliberately outlives the components that read it, so a flag
   * shared across conversations reports thread A's recovery as thread B's. It would
   * disable B's buttons for work that is not B's, and A's completion would clear
   * B's spinner while B's own read was still in flight — re-enabling the control and
   * permitting a second concurrent recovery.
   */
  recovering: string | null
  transport: AssistantTransport

  openThread: (threadId: string | null) => void
  /**
   * Records a listing.
   *
   * `read` is false for a failed one, and that is not bookkeeping: `listRead` gates
   * whether an empty list means "no conversations" or "no answer yet", and a failed
   * read has not answered. Marking it read would let one blocked request close the
   * open conversation.
   */
  setThreads: (threads: Thread[], problem: string | null, read?: boolean) => void
  setLastSent: (content: string) => void
  updateSession: (
    forThreadId: string | null,
    patch: (current: RunSession) => Partial<RunSession>,
  ) => void
  /** Marks a thread's recovery read as outstanding, or clears it with null. */
  setRecovering: (threadId: string | null) => void
}

export type AssistantStore = ReturnType<typeof createAssistantStore>

export function createAssistantStore() {
  return createStore<AssistantState>()((set) => ({
    threads: [],
    listRead: false,
    listProblem: null,
    openThreadId: null,
    session: emptyRunSession(null),
    lastSent: "",
    recovering: null,
    transport: { abort: null, turnKey: null, loadedThreadId: null, listLoaded: false },

    openThread: (threadId) => set({ openThreadId: threadId }),
    setThreads: (threads, problem, read = true) =>
      // `listRead` only ever moves forward: a failed refresh after a successful read
      // must not take the list back to "no answer yet".
      set((state) => ({
        threads,
        listProblem: problem,
        listRead: state.listRead || read,
      })),
    setLastSent: (content) => set({ lastSent: content }),
    setRecovering: (threadId) => set({ recovering: threadId }),

    /** Applies a patch, unless the thread it was computed for is no longer open. */
    updateSession: (forThreadId, patch) =>
      set((state) => {
        const base =
          state.session.threadId === forThreadId
            ? state.session
            : emptyRunSession(forThreadId)
        return { session: { ...base, ...patch(base) } }
      }),
  }))
}
