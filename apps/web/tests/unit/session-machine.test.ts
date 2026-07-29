import { describe, expect, it } from "vitest"

import type { GradeResult, NextQuestion, ReadyQuestion } from "@/lib/api/types"
import { backoffDelay, MAX_POLL_ATTEMPTS } from "@/lib/study/backoff"
import {
  canSubmit,
  initialSessionState,
  sessionReducer,
  type Phase,
  type SessionEvent,
  type SessionMachineState,
} from "@/lib/study/session-machine"

/**
 * The session lifecycle reducer — the priority module of phase 13.
 *
 * Every decision the study screen makes is a function of the previous state and one
 * event, so the whole lifecycle is asserted here without a server: each transition,
 * the fallback consequence, the consume-once desync recovery, the quota path, scope
 * invalidation, and the `question_not_assessable` desync.
 */

/** A ready assessment question. Overridable so a test can vary one field. */
function ready(overrides: Partial<ReadyQuestion> = {}): ReadyQuestion {
  return {
    state: "ready",
    renderFormat: "single_choice",
    questionId: 42,
    senseId: 7,
    interactionMode: "assessment",
    requestedLevel: 3,
    servedLevel: 3,
    isFallback: false,
    payload: { stem: "pick one", options: ["a", "b"] },
    ...overrides,
  } as ReadyQuestion
}

/** Drives the reducer from the initial state through a sequence of events. */
function run(...events: SessionEvent[]): SessionMachineState {
  return events.reduce(sessionReducer, initialSessionState())
}

/** Puts the machine in `asking` by delivering a ready question. */
function asking(question: ReadyQuestion = ready()): SessionMachineState {
  return sessionReducer(initialSessionState(), { type: "next_received", next: question })
}

describe("initialSessionState", () => {
  it("starts advancing with zeroed counters", () => {
    const state = initialSessionState()
    expect(state.phase.kind).toBe("advancing")
    expect(state.pollAttempt).toBe(0)
    expect(state.roundIndex).toBe(0)
    expect(state.roundServed).toBe(0)
    expect(state.answered).toBe(0)
    expect(state.correct).toBe(0)
  })

  it("seeds the round position from a resumed session", () => {
    const state = initialSessionState({ roundIndex: 2, roundServed: 4 })
    expect(state.roundIndex).toBe(2)
    expect(state.roundServed).toBe(4)
  })

  it("treats null seed fields as zero", () => {
    const state = initialSessionState({ roundIndex: null, roundServed: null })
    expect(state.roundIndex).toBe(0)
    expect(state.roundServed).toBe(0)
  })
})

describe("next_received", () => {
  it("moves to asking, resets the poll counter, and counts the served question", () => {
    const state = asking()
    expect(state.phase.kind).toBe("asking")
    expect(state.pollAttempt).toBe(0)
    expect(state.roundServed).toBe(1)
    if (state.phase.kind === "asking") {
      expect(state.phase.submitting).toBe(false)
      expect(state.phase.verdict).toBeNull()
      expect(state.phase.pendingTaskId).toBeNull()
      expect(state.phase.notice).toBeNull()
    }
  })

  it("enters a break at the reported round and restarts the per-round count", () => {
    let state = asking()
    expect(state.roundServed).toBe(1)
    const brk: NextQuestion = { state: "break", roundIndex: 1 }
    state = sessionReducer(state, { type: "next_received", next: brk })
    expect(state.phase.kind).toBe("break")
    if (state.phase.kind === "break") expect(state.phase.roundIndex).toBe(1)
    expect(state.roundIndex).toBe(1)
    expect(state.roundServed).toBe(0)
  })

  it("finishes on exhausted", () => {
    const state = sessionReducer(initialSessionState(), {
      type: "next_received",
      next: { state: "exhausted" },
    })
    expect(state.phase.kind).toBe("finished")
  })

  it("polls on preparing, incrementing the attempt without leaving advancing", () => {
    const state = sessionReducer(initialSessionState(), {
      type: "next_received",
      next: { state: "preparing" },
    })
    expect(state.phase.kind).toBe("preparing")
    expect(state.pollAttempt).toBe(1)
  })

  it("polls on waiting via the settling surface", () => {
    const state = sessionReducer(initialSessionState(), {
      type: "next_received",
      next: { state: "waiting" },
    })
    expect(state.phase.kind).toBe("settling")
    expect(state.pollAttempt).toBe(1)
  })

  it("stalls once the poll budget is spent rather than polling forever", () => {
    let state = initialSessionState()
    for (let i = 0; i < MAX_POLL_ATTEMPTS; i++) {
      state = sessionReducer(state, { type: "next_received", next: { state: "preparing" } })
    }
    expect(state.pollAttempt).toBe(MAX_POLL_ATTEMPTS)
    expect(state.phase.kind).toBe("stalled")
  })

  it("carries the isFallback flag through onto the asked question", () => {
    const state = asking(ready({ isFallback: true, servedLevel: 2 }))
    if (state.phase.kind === "asking") {
      expect(state.phase.question.isFallback).toBe(true)
      expect(state.phase.question.servedLevel).toBe(2)
    }
  })
})

describe("poll_again vs advance", () => {
  it("advance resets the poll counter so a retry from a stall gets a fresh budget", () => {
    let state = sessionReducer(initialSessionState(), {
      type: "next_received",
      next: { state: "preparing" },
    })
    expect(state.pollAttempt).toBe(1)
    state = sessionReducer(state, { type: "advance" })
    expect(state.phase.kind).toBe("advancing")
    expect(state.pollAttempt).toBe(0)
  })

  it("poll_again preserves the counter so the budget is actually spent", () => {
    let state = sessionReducer(initialSessionState(), {
      type: "next_received",
      next: { state: "preparing" },
    })
    expect(state.pollAttempt).toBe(1)
    state = sessionReducer(state, { type: "poll_again" })
    expect(state.phase.kind).toBe("advancing")
    expect(state.pollAttempt).toBe(1)
  })
})

describe("answer lifecycle", () => {
  it("marks submitting and clears any notice on answer_started", () => {
    let state = asking()
    state = sessionReducer(state, { type: "answer_started" })
    if (state.phase.kind === "asking") {
      expect(state.phase.submitting).toBe(true)
      expect(state.phase.notice).toBeNull()
    }
  })

  it("ignores answer_started when not asking", () => {
    const state = sessionReducer(initialSessionState(), { type: "answer_started" })
    expect(state.phase.kind).toBe("advancing")
  })

  it("settles a graded correct answer into a verdict and counts it", () => {
    let state = asking()
    const grade: GradeResult = {
      responseId: "resp-1",
      gradeStatus: "graded",
      senseId: 7,
      renderFormat: "single_choice",
      isCorrect: true,
      gradeScore: 100,
      gradeFeedback: "nice",
      masteryBefore: 20,
      masteryAfter: 35,
    }
    state = sessionReducer(state, { type: "answer_graded", grade })
    expect(state.answered).toBe(1)
    expect(state.correct).toBe(1)
    if (state.phase.kind === "asking") {
      expect(state.phase.submitting).toBe(false)
      expect(state.phase.pendingTaskId).toBeNull()
      expect(state.phase.verdict?.isCorrect).toBe(true)
      expect(state.phase.verdict?.masteryAfter).toBe(35)
    }
  })

  it("counts an incorrect answer as answered but not correct", () => {
    let state = asking()
    const grade: GradeResult = {
      responseId: "resp-2",
      gradeStatus: "graded",
      senseId: 7,
      renderFormat: "single_choice",
      isCorrect: false,
    }
    state = sessionReducer(state, { type: "answer_graded", grade })
    expect(state.answered).toBe(1)
    expect(state.correct).toBe(0)
    if (state.phase.kind === "asking") expect(state.phase.verdict?.isCorrect).toBe(false)
  })

  it("counts a pending grade on submission and holds the task id without a verdict", () => {
    let state = asking()
    const grade: GradeResult = {
      responseId: "resp-3",
      gradeStatus: "pending",
      senseId: 7,
      renderFormat: "free_text",
      taskId: "task-99",
    }
    state = sessionReducer(state, { type: "answer_graded", grade })
    // Counted on submission so the running total never drops an outstanding grade.
    expect(state.answered).toBe(1)
    expect(state.correct).toBe(0)
    if (state.phase.kind === "asking") {
      expect(state.phase.pendingTaskId).toBe("task-99")
      expect(state.phase.verdict).toBeNull()
    }
  })

  it("ignores a grade that arrives when not asking", () => {
    const grade: GradeResult = {
      responseId: "resp-4",
      gradeStatus: "graded",
      senseId: 7,
      renderFormat: "single_choice",
      isCorrect: true,
    }
    const state = sessionReducer(initialSessionState(), { type: "answer_graded", grade })
    expect(state.phase.kind).toBe("advancing")
    expect(state.answered).toBe(0)
  })
})

describe("next_failed", () => {
  it("stalls, not errors, when preparation retries are exhausted", () => {
    const state = sessionReducer(asking(), {
      type: "next_failed",
      code: "question_preparation_exhausted",
    })
    expect(state.phase.kind).toBe("stalled")
    expect(state.pollAttempt).toBe(0)
  })

  it("finishes on session_not_found, since a gone session is also a completed one", () => {
    const state = sessionReducer(asking(), { type: "next_failed", code: "session_not_found" })
    expect(state.phase.kind).toBe("finished")
  })

  it("stops the session on an unclassified next failure", () => {
    const state = sessionReducer(asking(), { type: "next_failed", code: "http_error" })
    expect(state.phase.kind).toBe("stopped")
    if (state.phase.kind === "stopped") expect(state.phase.code).toBe("http_error")
  })
})

describe("answer_failed", () => {
  it.each([
    "question_not_issued_for_session",
    "question_not_available",
    "question_not_assessable",
  ])("re-polls /next on the desync code %s rather than resubmitting", (code) => {
    const state = sessionReducer(asking(), { type: "answer_failed", code })
    // Recovery is advancing to re-poll; the server consumed the delivery claim, so
    // a resubmit walks into the same rejection.
    expect(state.phase.kind).toBe("advancing")
    expect(state.pollAttempt).toBe(0)
  })

  it("stops with the scope-changed message when the deck changed mid-session", () => {
    const state = sessionReducer(asking(), { type: "answer_failed", code: "session_scope_changed" })
    expect(state.phase.kind).toBe("stopped")
    if (state.phase.kind === "stopped") {
      expect(state.phase.code).toBe("session_scope_changed")
      expect(state.phase.message).toContain("was not recorded")
    }
  })

  it("finishes on session_not_found", () => {
    const state = sessionReducer(asking(), { type: "answer_failed", code: "session_not_found" })
    expect(state.phase.kind).toBe("finished")
  })

  it("leaves the question on screen with a notice when the grading quota is spent", () => {
    const state = sessionReducer(asking(), {
      type: "answer_failed",
      code: "answer_grading_quota_exceeded",
    })
    // A spent quota is not a broken session: the learner reads the reason and moves on.
    expect(state.phase.kind).toBe("asking")
    if (state.phase.kind === "asking") {
      expect(state.phase.submitting).toBe(false)
      expect(state.phase.notice).toBeTruthy()
    }
  })

  it("stops on a generic answer failure when not asking", () => {
    const state = sessionReducer(initialSessionState(), {
      type: "answer_failed",
      code: "http_error",
    })
    expect(state.phase.kind).toBe("stopped")
  })
})

describe("canSubmit", () => {
  const base = ready()

  it("permits a fresh assessment question", () => {
    const phase: Phase = {
      kind: "asking",
      question: base,
      submitting: false,
      verdict: null,
      pendingTaskId: null,
      notice: null,
    }
    expect(canSubmit(phase)).toBe(true)
  })

  it("forbids submitting an exposure card", () => {
    const phase: Phase = {
      kind: "asking",
      question: ready({ interactionMode: "exposure", questionId: null }),
      submitting: false,
      verdict: null,
      pendingTaskId: null,
      notice: null,
    }
    expect(canSubmit(phase)).toBe(false)
  })

  it.each([
    ["while submitting", { submitting: true }],
    ["with a verdict already shown", { verdict: { isCorrect: true, score: null, feedback: null, reveal: null, masteryBefore: null, masteryAfter: null } }],
    ["with a grade pending", { pendingTaskId: "task-1" }],
  ])("forbids submitting %s", (_label, patch) => {
    const phase: Phase = {
      kind: "asking",
      question: base,
      submitting: false,
      verdict: null,
      pendingTaskId: null,
      notice: null,
      ...(patch as object),
    }
    expect(canSubmit(phase)).toBe(false)
  })

  it("forbids submitting from a non-asking phase", () => {
    expect(canSubmit({ kind: "advancing" })).toBe(false)
    expect(canSubmit({ kind: "finished" })).toBe(false)
  })
})

describe("backoffDelay", () => {
  it("grows geometrically then clamps at the ceiling", () => {
    expect(backoffDelay(1)).toBe(600)
    expect(backoffDelay(2)).toBe(1_200)
    expect(backoffDelay(3)).toBe(2_400)
    // Clamped: 600 * 2^3 = 4800 would exceed the 4000ms ceiling.
    expect(backoffDelay(4)).toBe(4_000)
    expect(backoffDelay(99)).toBe(4_000)
  })

  it("treats a zero or negative attempt as the first", () => {
    expect(backoffDelay(0)).toBe(600)
    expect(backoffDelay(-5)).toBe(600)
  })
})

describe("a full session walk", () => {
  it("advances from a question through a graded answer to exhaustion", () => {
    let state = run(
      { type: "next_received", next: ready() },
      { type: "answer_started" },
      {
        type: "answer_graded",
        grade: {
          responseId: "r",
          gradeStatus: "graded",
          senseId: 7,
          renderFormat: "single_choice",
          isCorrect: true,
        },
      },
      { type: "advance" },
    )
    expect(state.phase.kind).toBe("advancing")
    expect(state.answered).toBe(1)
    expect(state.correct).toBe(1)

    state = sessionReducer(state, { type: "next_received", next: { state: "exhausted" } })
    expect(state.phase.kind).toBe("finished")
  })
})
