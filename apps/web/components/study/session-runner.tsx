"use client"

import { useCallback, useEffect, useReducer, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { advanceSession, readSession, submitAnswer } from "@/lib/actions/study"
import type { SessionState } from "@/lib/api/types"
import { useTaskSnapshot } from "@/lib/realtime/use-task-snapshot"
import { useActivityActions, useActivityStore, useUiStore } from "@/lib/stores/store-provider"
import { backoffDelay } from "@/lib/study/backoff"
import { readPendingGrade } from "@/lib/study/grade-snapshot"
import {
  canSubmit,
  initialSessionState,
  sessionReducer,
  type Verdict,
} from "@/lib/study/session-machine"
import { ArrowRightIcon, XIcon } from "@/lib/icons"

import { CalibrationNote } from "./calibration-note"
import { ExitSessionDialog } from "./exit-session-dialog"
import { ExposureCard } from "./exposure-card"
import { PendingGradePanel } from "./pending-grade-panel"
import { PreparingPanel, SettlingPanel, StalledPanel } from "./polling-panel"
import { QuestionBody } from "./question-body"
import { choiceCount } from "./single-choice-question"
import { QuestionStage } from "./question-stage"
import { RoundBreakPanel } from "./round-break-panel"
import { RoundIndicator } from "./round-indicator"
import { SessionRecap } from "./session-recap"
import { SessionStoppedPanel } from "./session-stopped-panel"
import { VerdictPanel } from "./verdict-panel"

/**
 * The study loop.
 *
 * This is the only component that calls `/next` or `/answers`, and it is why both go
 * through server actions rather than a query client: `/next` mutates despite being a
 * GET, so it must never be retried, refetched, prefetched, or run twice concurrently
 * for one session. The action layer single-flights per session id; this component
 * makes sure a call is only issued in response to a state that asked for one.
 *
 * Every decision lives in the reducer. The effects here do I/O and dispatch the
 * result, which is what keeps the lifecycle testable without a browser.
 */
export function SessionRunner({
  sessionId,
  initialSession,
  deckTitle,
}: {
  sessionId: string
  /** The session as read on the server, so a reload resumes rather than restarts. */
  initialSession: SessionState
  deckTitle: string
}) {
  const [state, dispatch] = useReducer(
    sessionReducer,
    initialSession.status === "completed"
      ? // A finished session goes straight to its recap. Calling `/next` on it would
        // 404, and the durable summary already holds everything the screen shows.
        { ...initialSessionState(), phase: { kind: "finished" as const } }
      : initialSessionState({
          roundIndex: initialSession.roundIndex,
          // The live read carries no per-round delivery count, so the indicator
          // starts this round at zero rather than inventing a position within it.
          roundServed: 0,
        }),
  )

  const [exiting, setExiting] = useState(false)
  const { phase } = state

  const nodeId = initialSession.nodeId ?? null
  const maxPerRound = initialSession.maxPerRound ?? null

  // --- live-session publication -------------------------------------------------
  //
  // Adding or removing a sense bumps the deck's structural generation, which the API
  // compares on every `/next` and `/answers`. So the palette and the deck views have
  // to know a session is open before they offer that mutation, and this screen is the
  // only place that knows.
  //
  // The publication outlives this screen, because the session does. Walking away
  // neither ends the session nor releases its scope generation: the Redis meta stands
  // until the session completes or expires, and this URL resumes it. Clearing on
  // unmount is what made the warning unreachable — the library is the only screen an
  // add can be started from, so by the time one was, the store had already forgotten
  // there was a session to warn about. It is cleared when the session actually ends,
  // and it is per-tab in memory, so a reload forgets it too.
  const setLiveSession = useUiStore((store) => store.setLiveSession)
  const sessionOver = phase.kind === "finished" || phase.kind === "stopped"
  useEffect(() => {
    if (!nodeId) return
    setLiveSession(sessionOver ? null : { sessionId, nodeId, deckTitle })
  }, [sessionId, nodeId, deckTitle, sessionOver, setLiveSession])

  // --- the `/next` loop ---------------------------------------------------------
  //
  // The ref is the near guard against a second concurrent call: React runs effects
  // twice in development, and a duplicate `/next` strands a question permanently. The
  // action layer single-flights as well, which is the far guard.
  const advancing = useRef(false)

  const runAdvance = useCallback(async () => {
    if (advancing.current) return
    advancing.current = true
    try {
      const result = await advanceSession(sessionId)
      dispatch(
        result.success
          ? { type: "next_received", next: result.data }
          : { type: "next_failed", code: result.code },
      )
    } finally {
      advancing.current = false
    }
  }, [sessionId])

  useEffect(() => {
    if (phase.kind !== "advancing") return
    void runAdvance()
  }, [phase.kind, runAdvance])

  // A polled state waits out its backoff, then asks again through the same guard.
  // `poll_again` preserves the attempt counter, so the budget actually drains and the
  // screen reaches a stall instead of polling a mutating endpoint forever.
  useEffect(() => {
    if (phase.kind !== "preparing" && phase.kind !== "settling") return
    const timer = setTimeout(() => dispatch({ type: "poll_again" }), backoffDelay(state.pollAttempt))
    return () => clearTimeout(timer)
  }, [phase.kind, state.pollAttempt])

  // --- the draft answer ---------------------------------------------------------
  //
  // Held next to the question it belongs to rather than cleared by an effect. Writing
  // state during an effect would run a frame late, so the previous answer would show
  // under the new question; keying it means a new question derives an empty draft.
  const questionKey =
    phase.kind === "asking" ? `${phase.question.senseId}:${phase.question.questionId}` : null
  const [draft, setDraft] = useState<{ key: string | null; answer: string }>({
    key: questionKey,
    answer: "",
  })
  const answer = draft.key === questionKey ? draft.answer : ""
  const setAnswer = useCallback(
    (next: string) => setDraft({ key: questionKey, answer: next }),
    [questionKey],
  )

  // --- submission ---------------------------------------------------------------

  const { register } = useActivityActions()

  // The near guard against a second submission of the same question, and the
  // counterpart to `advancing` above.
  //
  // `canSubmit` reads the phase captured by *this* render, and `dispatch` does not
  // update it synchronously — so two Enters landing before React commits both see
  // `submitting: false` and both post. Only one can win the server's consume-once
  // bind; the loser comes back `question_not_issued_for_session`, which the reducer
  // correctly reads as a desync and re-polls `/next`. The cost is the winner's
  // verdict: it is wiped off the screen before the learner sees it, and the question
  // it belonged to is behind them.
  //
  // Keyed by the question rather than held as a boolean, for the same reason the
  // draft above is keyed: a boolean has to be released, and the window between
  // releasing it and React committing the new phase is exactly the window this
  // exists to close. A new question carries a new key, so nothing is released at all.
  const submitted = useRef<string | null>(null)

  const onSubmit = useCallback(async () => {
    if (phase.kind !== "asking" || !canSubmit(phase)) return
    const id = phase.question.questionId
    if (id == null) return

    const key = `${phase.question.senseId}:${id}`
    if (submitted.current === key) return
    submitted.current = key
    dispatch({ type: "answer_started" })
    const result = await submitAnswer(sessionId, id, answer)

    if (!result.success) {
      // A failure may leave the question on screen and answerable — a spent grading
      // quota does exactly that — so the guard reopens. The codes that do not leave
      // it answerable move the phase on, which changes the key anyway.
      submitted.current = null
      dispatch({ type: "answer_failed", code: result.code })
      return
    }

    // A pending grade is registered with the activity centre so it outlives this
    // screen: the id is persisted there and re-subscribed on the next mount, which is
    // what lets a reload still reach the verdict.
    if (result.data.gradeStatus === "pending" && result.data.taskId) {
      register({ taskId: result.data.taskId, kind: "grade", senseId: result.data.senseId })
    }

    dispatch({ type: "answer_graded", grade: result.data })
  }, [phase, sessionId, answer, register])

  // --- an asynchronous grade ----------------------------------------------------
  //
  // Derived at render from the snapshot rather than copied into the reducer. The task
  // id is persisted, so a reload re-subscribes and the replayed snapshot rebuilds this
  // same verdict; a reducer copy would be lost by exactly that reload.
  const pendingTaskId = phase.kind === "asking" ? phase.pendingTaskId : null
  const snapshot = useTaskSnapshot(pendingTaskId)
  const pendingGrade = pendingTaskId ? readPendingGrade(snapshot) : null

  // `stale` means a re-subscribe was denied, which is the only case a reconnect
  // affordance is honest about. A dropped socket is not staleness: the proxy replays
  // the latest snapshot, so reconnecting settles the task on its own.
  const staleGrade = useActivityStore((store) =>
    pendingTaskId
      ? (store.tasks.find((task) => task.taskId === pendingTaskId)?.stale ?? false)
      : false,
  )

  const settledVerdict: Verdict | null =
    phase.kind === "asking"
      ? (phase.verdict ?? (pendingGrade?.kind === "settled" ? pendingGrade.verdict : null))
      : null

  const onAdvance = useCallback(() => dispatch({ type: "advance" }), [])

  // --- keyboard operation -------------------------------------------------------
  //
  // The whole session is reachable without a pointer: digits pick a choice, Enter
  // commits or moves on, Escape asks to leave. Bound at the document rather than on
  // each control because the key that matters most (Enter to submit) has to work
  // while focus sits in the answer input, which is not inside the footer button.
  // Every screen whose only action is "carry on": a graded question, a grade that
  // will not arrive, an exposure card, and a round break. Enter means the same thing
  // on all four, so they share one branch rather than each growing a special case.
  const advanceOnEnter =
    settledVerdict !== null ||
    pendingGrade?.kind === "failed" ||
    phase.kind === "break" ||
    (phase.kind === "asking" && phase.question.renderFormat === "flashcard")

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.altKey) return

      // While the exit dialog is open it owns the keyboard entirely. Without this
      // the two fight over the same event: Escape would reach the dialog's own
      // dismiss *and* this handler, which would immediately reopen what was just
      // closed, and Enter would advance the session behind a modal asking whether
      // to leave it.
      if (exiting) return

      if (event.key === "Escape") {
        event.preventDefault()
        setExiting(true)
        return
      }

      if (event.key === "Enter" && advanceOnEnter) {
        event.preventDefault()
        onAdvance()
        return
      }

      if (phase.kind !== "asking") return

      // In a textarea Enter is a newline, so committing free text needs a modifier.
      // Anywhere else a bare Enter submits.
      const inTextarea =
        event.target instanceof HTMLElement && event.target.tagName === "TEXTAREA"
      if (event.key === "Enter" && (!inTextarea || event.ctrlKey)) {
        if (!canSubmit(phase) || answer.trim().length === 0) return
        event.preventDefault()
        void onSubmit()
        return
      }

      // Digits select an option, but only where digits are not themselves an answer:
      // typing "1" into a free-text box must stay a character.
      if (
        phase.question.renderFormat === "single_choice" &&
        canSubmit(phase) &&
        /^[1-9]$/.test(event.key)
      ) {
        const index = Number(event.key) - 1
        if (index >= choiceCount(phase.question)) return
        event.preventDefault()
        setAnswer(String(index))
      }
    }

    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [phase, answer, exiting, advanceOnEnter, onAdvance, onSubmit, setAnswer])

  // --- the recap ----------------------------------------------------------------
  //
  // Read from the server rather than accumulated here. Reaching `exhausted` deletes
  // the live namespace, so only the persisted summary is left, and reading it is what
  // makes this screen survive a reload.
  const [recap, setRecap] = useState<SessionState | null>(
    initialSession.status === "completed" ? initialSession : null,
  )
  useEffect(() => {
    if (phase.kind !== "finished" || recap) return
    let active = true
    void readSession(sessionId).then((result) => {
      if (active && result.success) setRecap(result.data)
    })
    return () => {
      active = false
    }
  }, [phase.kind, recap, sessionId])

  // --- surfaces -----------------------------------------------------------------

  const exitDialog = (
    <ExitSessionDialog open={exiting} onOpenChange={setExiting} nodeId={nodeId} />
  )

  const header = (
    <>
      <RoundIndicator
        roundIndex={state.roundIndex}
        served={state.roundServed}
        maxPerRound={maxPerRound}
      />
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={() => setExiting(true)}
        aria-label="Leave this session"
      >
        <XIcon />
      </Button>
    </>
  )

  function stage(children: React.ReactNode, withHeader = true) {
    return (
      <>
        <QuestionStage header={withHeader ? header : undefined}>{children}</QuestionStage>
        {exitDialog}
      </>
    )
  }

  if (phase.kind === "finished") {
    return stage(
      recap ? (
        <SessionRecap session={recap} nodeId={nodeId} />
      ) : (
        <CentredSpinner label="Loading your session summary" />
      ),
      false,
    )
  }

  if (phase.kind === "stopped") {
    return stage(<SessionStoppedPanel message={phase.message} nodeId={nodeId} />, false)
  }

  if (phase.kind === "stalled") {
    return stage(
      <StalledPanel
        message={phase.message}
        onRetry={onAdvance}
        onLeave={() => setExiting(true)}
        retrying={false}
      />,
    )
  }

  if (phase.kind === "break") {
    return stage(
      <RoundBreakPanel
        roundIndex={phase.roundIndex}
        answeredInRound={state.roundServed}
        onContinue={onAdvance}
        advancing={false}
      />,
    )
  }

  if (phase.kind === "preparing") {
    return stage(<PreparingPanel attempt={state.pollAttempt} />)
  }

  if (phase.kind === "settling") {
    return stage(<SettlingPanel attempt={state.pollAttempt} />)
  }

  if (phase.kind === "advancing") {
    return stage(<CentredSpinner label="Loading your next question" />)
  }

  // --- a question ---------------------------------------------------------------

  const { question } = phase

  // A flashcard is presented, never answered: its question id is null and the server
  // refuses an answer for it. So there is no submit control here at all, rather than a
  // disabled one. Narrowing on the render format also removes any need to cast below,
  // since every remaining format is an assessment.
  if (question.renderFormat === "flashcard") {
    return stage(<ExposureCard question={question} onAdvance={onAdvance} advancing={false} />)
  }

  // A grade that will not arrive still has to let the learner move on, so a failed
  // settlement counts as answered for the purpose of the continue control.
  const gradeFailed = pendingGrade?.kind === "failed"
  const answered = settledVerdict !== null
  const locked = phase.submitting || answered || pendingTaskId !== null

  return (
    <>
      <QuestionStage
        header={header}
        footer={
          answered || gradeFailed ? (
            <Button onClick={onAdvance} size="lg">
              Continue
              <ArrowRightIcon data-icon="inline-end" />
            </Button>
          ) : pendingTaskId ? null : (
            <Button
              onClick={onSubmit}
              disabled={!canSubmit(phase) || answer.trim().length === 0}
              size="lg"
            >
              {phase.submitting ? <Spinner data-icon="inline-start" /> : null}
              Submit
            </Button>
          )
        }
      >
        <QuestionBody
          question={question}
          answer={answer}
          onAnswer={setAnswer}
          disabled={locked}
        />

        <CalibrationNote
          requestedLevel={question.requestedLevel}
          servedLevel={question.servedLevel}
          isFallback={question.isFallback}
        />

        {phase.notice ? (
          <p className="text-sm text-muted-foreground">{phase.notice}</p>
        ) : null}

        {pendingTaskId && !answered ? (
          <PendingGradePanel
            stale={staleGrade}
            failed={gradeFailed}
            onReconnect={() => window.location.reload()}
          />
        ) : null}

        {settledVerdict ? (
          <VerdictPanel
            verdict={settledVerdict}
            renderFormat={question.renderFormat}
            question={question.renderFormat === "single_choice" ? question : undefined}
          />
        ) : null}
      </QuestionStage>
      {exitDialog}
    </>
  )
}

function CentredSpinner({ label }: { label: string }) {
  return (
    <div className="flex justify-center">
      <Spinner className="size-6 text-muted-foreground" aria-label={label} />
    </div>
  )
}
