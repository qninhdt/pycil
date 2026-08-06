/**
 * The session lifecycle as a pure reducer.
 *
 * No I/O lives here on purpose. Every decision the study screen makes — which
 * surface to show, whether an answer may be submitted, whether a failure is
 * recoverable by polling or ends the session — is a function of the previous
 * state and one event, so the whole lifecycle is testable without a server.
 *
 * The one rule this file exists to enforce: **an unhandled `/next` state is a
 * compile error.** The switch over the five-state union ends in `assertNever`,
 * so a sixth state added by the API fails the typecheck instead of rendering
 * nothing at runtime with no indication why.
 */

import { classifyErrorCode } from "@/lib/api/error-taxonomy"
import { assertNever, type GradeResult, type NextQuestion, type ReadyQuestion, type Reveal } from "@/lib/api/types"

import { isPollExhausted } from "./backoff"

/** A settled grade, from either settlement path. */
export interface Verdict {
  isCorrect: boolean | null
  score: number | null
  feedback: string | null
  reveal: Reveal | null
  masteryBefore: number | null
  masteryAfter: number | null
}

/**
 * What the screen is showing.
 *
 * `advancing` is both "a `/next` call is in flight" and "one should be issued":
 * the runner's effect keys off it, which keeps the decision to call in the
 * reducer rather than scattered across handlers.
 */
export type Phase =
  | { kind: "advancing" }
  | {
      kind: "asking"
      question: ReadyQuestion
      submitting: boolean
      /** Null until the answer is graded. Exposure never gets one. */
      verdict: Verdict | null
      /** Set while an asynchronous grade is outstanding. */
      pendingTaskId: string | null
      /** A recoverable problem stated in place, without leaving the question. */
      notice: string | null
    }
  | { kind: "break"; roundIndex: number }
  /**
   * Supply is being generated.
   *
   * `taskId` is what the runner subscribes to. When it is null no task was
   * started — the generation slot refused, or the cooldown has not elapsed — and
   * the bounded backoff is the only way forward, which is why the poll machinery
   * below still exists rather than being deleted outright.
   */
  | { kind: "preparing"; taskId: string | null }
  | { kind: "settling" }
  /** Polling gave up, or the server said supply is exhausted. Offers to wait on. */
  | { kind: "stalled"; message: string }
  | { kind: "finished" }
  | { kind: "stopped"; code: string; message: string }

export interface SessionMachineState {
  phase: Phase
  /** Consecutive polled responses. Reset by anything that is not a poll. */
  pollAttempt: number
  /** 0-based, as the server counts rounds. */
  roundIndex: number
  /** Questions delivered in the current round, for the round indicator. */
  roundServed: number
  /**
   * Every delivery this session has made, never reset.
   *
   * Distinct from `roundServed`, which restarts each round, and it exists to be an
   * *identity* rather than a statistic. A question is not unique within a session:
   * `restore_delivered` drops an id from the exclusion set so an aborted checkpoint
   * can be re-served, so the same sense and question can legitimately come back in
   * a later round. Anything guarding "have I already submitted this one" therefore
   * needs a counter, because the pair alone cannot tell the second delivery from
   * the first.
   */
  delivered: number
  /** Submissions made, whether or not their grade has settled. */
  answered: number
  correct: number
}

export type SessionEvent =
  | { type: "next_received"; next: NextQuestion }
  | { type: "next_failed"; code: string }
  | { type: "answer_started" }
  | { type: "answer_graded"; grade: GradeResult }
  | { type: "answer_failed"; code: string }
  /** The learner moves on: from a verdict, a break, an exposure, or a stall. */
  | { type: "advance" }
  /**
   * The backoff timer elapsed on a polled state.
   *
   * Distinct from `advance` because it must *not* reset the poll counter. Reusing
   * `advance` here would zero the count on every tick, so the budget could never be
   * spent and the screen would poll a mutating endpoint forever.
   */
  | { type: "poll_again" }
  /**
   * The supply task the screen was subscribed to reached a terminal state.
   *
   * Distinct from `advance` for the same reason `poll_again` is: the counter must
   * survive. A supply task that settles without producing a deliverable question
   * puts `/next` straight back into `preparing`, and if this reset the budget those
   * two would trade forever. The event makes the wait cheap, not unbounded.
   */
  | { type: "supply_settled" }

export function initialSessionState(seed?: {
  roundIndex?: number | null
  roundServed?: number | null
}): SessionMachineState {
  return {
    phase: { kind: "advancing" },
    pollAttempt: 0,
    roundIndex: seed?.roundIndex ?? 0,
    roundServed: seed?.roundServed ?? 0,
    delivered: 0,
    answered: 0,
    correct: 0,
  }
}

export function sessionReducer(
  state: SessionMachineState,
  event: SessionEvent,
): SessionMachineState {
  switch (event.type) {
    case "advance":
      // A deliberate move by the learner, so the poll budget starts fresh: an
      // explicit retry from a stall is exactly the case that should get one.
      return { ...state, phase: { kind: "advancing" }, pollAttempt: 0 }

    case "poll_again":
      // The counter survives on purpose: it is what the poll budget is measured
      // against, and only a real question, a break, or the learner resets it.
      return { ...state, phase: { kind: "advancing" } }

    case "supply_settled":
      // Only from `preparing`. A settled task arriving in any other phase is a
      // late event for a wait the screen has already left — the learner may have
      // retried from a stall, or a question may have arrived by another route —
      // and acting on it would yank them out of whatever they moved on to.
      return state.phase.kind === "preparing"
        ? { ...state, phase: { kind: "advancing" } }
        : state

    case "next_received":
      return applyNext(state, event.next)

    case "next_failed":
      return applyNextFailure(state, event.code)

    case "answer_started":
      return state.phase.kind === "asking"
        ? { ...state, phase: { ...state.phase, submitting: true, notice: null } }
        : state

    case "answer_graded":
      return applyGrade(state, event.grade)

    case "answer_failed":
      return applyAnswerFailure(state, event.code)

    default:
      return assertNever(event)
  }
}

function applyNext(state: SessionMachineState, next: NextQuestion): SessionMachineState {
  switch (next.state) {
    case "ready":
      return {
        ...state,
        pollAttempt: 0,
        roundServed: state.roundServed + 1,
        delivered: state.delivered + 1,
        phase: {
          kind: "asking",
          question: next,
          submitting: false,
          verdict: null,
          pendingTaskId: null,
          notice: null,
        },
      }

    case "break":
      // The server reports the round being entered, and the counter restarts
      // with it: pips are per round, not per session.
      return {
        ...state,
        pollAttempt: 0,
        roundIndex: next.roundIndex,
        roundServed: 0,
        phase: { kind: "break", roundIndex: next.roundIndex },
      }

    case "preparing":
      return poll(state, { kind: "preparing", taskId: next.taskId }, PREPARING_STALL)

    case "waiting":
      return poll(state, { kind: "settling" }, SETTLING_STALL)

    case "exhausted":
      return { ...state, pollAttempt: 0, phase: { kind: "finished" } }

    default:
      // A sixth `/next` state cannot reach production: this fails the typecheck.
      return assertNever(next)
  }
}

/** Advances the poll counter, or stalls once the budget is spent. */
function poll(
  state: SessionMachineState,
  phase: Phase,
  stallMessage: string,
): SessionMachineState {
  const pollAttempt = state.pollAttempt + 1
  return {
    ...state,
    pollAttempt,
    phase: isPollExhausted(pollAttempt) ? { kind: "stalled", message: stallMessage } : phase,
  }
}

const PREPARING_STALL =
  "Your next question is still being written. This sometimes takes a while."

const SETTLING_STALL = "An answer is still being marked."

function applyNextFailure(state: SessionMachineState, code: string): SessionMachineState {
  // Supply ran out of retries. Not a broken session: the work exists and the
  // learner may keep waiting for it.
  if (code === "question_preparation_exhausted") {
    return { ...state, pollAttempt: 0, phase: { kind: "stalled", message: PREPARING_STALL } }
  }

  // The session is gone from the round store, which is also what completing it
  // looks like. The recap reads the durable summary, so finishing is correct here
  // rather than reporting an error over a session that may simply be over.
  if (code === "session_not_found") {
    return { ...state, pollAttempt: 0, phase: { kind: "finished" } }
  }

  return stop(state, code)
}

function applyGrade(state: SessionMachineState, grade: GradeResult): SessionMachineState {
  if (state.phase.kind !== "asking") return state

  // Counted on submission rather than on settlement, so the running total does
  // not drop a free-text answer whose grade is still outstanding.
  const answered = state.answered + 1

  if (grade.gradeStatus === "pending") {
    return {
      ...state,
      answered,
      phase: {
        ...state.phase,
        submitting: false,
        pendingTaskId: grade.taskId ?? null,
        verdict: null,
      },
    }
  }

  return {
    ...state,
    answered,
    correct: state.correct + (grade.isCorrect ? 1 : 0),
    phase: {
      ...state.phase,
      submitting: false,
      pendingTaskId: null,
      verdict: {
        isCorrect: grade.isCorrect ?? null,
        score: grade.gradeScore ?? null,
        feedback: grade.gradeFeedback ?? null,
        reveal: grade.reveal ?? null,
        masteryBefore: grade.masteryBefore ?? null,
        masteryAfter: grade.masteryAfter ?? null,
      },
    },
  }
}

/**
 * Codes that mean "this question is not yours to answer any more".
 *
 * Recovery is re-polling `/next`, never resubmitting: the server consumed the
 * delivery claim, and a resubmit walks into the same rejection. The claim is
 * reopened server-side, so the sense returns in a later round.
 */
const DESYNC_CODES = new Set([
  "question_not_issued_for_session",
  "question_not_available",
  "question_not_assessable",
])

function applyAnswerFailure(state: SessionMachineState, code: string): SessionMachineState {
  if (DESYNC_CODES.has(code)) {
    return { ...state, phase: { kind: "advancing" }, pollAttempt: 0 }
  }

  if (code === "session_scope_changed") return stop(state, code)

  if (code === "session_not_found") {
    return { ...state, pollAttempt: 0, phase: { kind: "finished" } }
  }

  // Everything else — the grading quota included — leaves the question on screen
  // with the reason stated. A spent quota is not a broken session: the learner
  // moves on and the session still reaches its end.
  if (state.phase.kind !== "asking") return stop(state, code)
  return {
    ...state,
    phase: {
      ...state.phase,
      submitting: false,
      notice: classifyErrorCode(code).message,
    },
  }
}

function stop(state: SessionMachineState, code: string): SessionMachineState {
  const message =
    code === "session_scope_changed"
      ? // The generation check runs before the delivery claim is consumed, so an
        // answer sent into this failure was never recorded. Saying otherwise would
        // credit work the learner did not get.
        "This deck changed while you were studying, so the session ended. Your last answer was not recorded; everything before it was."
      : classifyErrorCode(code).message

  return { ...state, pollAttempt: 0, phase: { kind: "stopped", code, message } }
}

/** Whether an answer may be submitted for what is on screen right now. */
export function canSubmit(phase: Phase): boolean {
  return (
    phase.kind === "asking" &&
    !phase.submitting &&
    phase.verdict === null &&
    phase.pendingTaskId === null &&
    phase.question.interactionMode !== "exposure" &&
    phase.question.questionId !== null
  )
}
