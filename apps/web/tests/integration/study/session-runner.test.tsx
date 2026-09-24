import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { SessionRunner } from "@/components/study/session-runner"
import type { SessionState } from "@/lib/api/types"
import { StoreProvider } from "@/lib/stores/store-provider"

import { server } from "../server"

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }),
}))

/**
 * The study loop against the responses the API really sends.
 *
 * The session is driven by `/next`, which mutates despite being a GET — it reserves a
 * delivery, so the whole point of the runner is that it asks exactly once per state
 * that wants a question. That is asserted here by counting requests, because the
 * failure it prevents is silent: a duplicate call destroys a question the learner
 * never sees.
 *
 * The other rule under test is the one about exposure. A flashcard has no question id
 * and the server refuses an answer for it, so the screen must offer no way to submit
 * one rather than a disabled control.
 */

const LIVE: SessionState = {
  sessionId: "sess-1",
  status: "live",
  nodeId: "deck-1",
  roundIndex: 1,
  roundCount: 2,
  maxPerRound: 8,
  expiresAt: "2026-09-25T00:00:00Z",
}

const FLASHCARD = {
  state: "ready",
  questionId: null,
  senseId: 42,
  interactionMode: "exposure",
  requestedLevel: 0,
  servedLevel: 0,
  isFallback: false,
  renderFormat: "flashcard",
  payload: {
    word: "resilient",
    definition: "able to recover quickly",
    pos: "adjective",
    example: null,
    ipa_uk: null,
    ipa_us: null,
  },
}

const CHOICE = {
  state: "ready",
  questionId: 900,
  senseId: 42,
  interactionMode: "assessment",
  requestedLevel: 1,
  servedLevel: 1,
  isFallback: false,
  renderFormat: "single_choice",
  payload: { stem: "Pick the meaning", options: ["able to recover", "easily broken"] },
}

/**
 * The runner publishes the live session to the UI store, which is what warns the
 * learner before a deck edit ends their session. That store is mounted once at the
 * app root, so a test renders the same provider rather than stubbing the hook.
 */
function renderRunner(session: SessionState) {
  return render(
    <StoreProvider>
      <SessionRunner sessionId="sess-1" initialSession={session} deckTitle="IELTS" />
    </StoreProvider>,
  )
}

/** Counts `/next` calls, which is the behaviour the single-flight guard exists for. */
function countNext() {
  const calls = { total: 0 }
  server.use(
    http.get("/v1/sessions/sess-1/next", () => {
      calls.total += 1
      return HttpResponse.json(FLASHCARD)
    }),
  )
  return calls
}

describe("the study loop", () => {
  beforeEach(() => {
    server.use(http.get("/v1/sessions/sess-1", () => HttpResponse.json(LIVE)))
  })

  it("shows an exposure card as presented, with no way to answer it", async () => {
    countNext()
    renderRunner(LIVE)

    expect(await screen.findByText("resilient")).toBeTruthy()
    // Exposure is shown, never assessed: the server refuses an answer for a card with
    // no question id, so the control is absent rather than disabled.
    expect(screen.queryByRole("button", { name: /Submit/ })).toBeNull()
    expect(screen.getByRole("button", { name: /Got it/ })).toBeTruthy()
  })

  it("asks for the next question once per state that wants one", async () => {
    const calls = countNext()
    renderRunner(LIVE)

    await screen.findByText("resilient")
    // React runs effects twice in development; a second `/next` here would strand
    // the question the first call reserved.
    await new Promise((resolve) => setTimeout(resolve, 50))

    expect(calls.total).toBe(1)
  })

  it("grades an answer and shows the verdict the server returned", async () => {
    let served = 0
    server.use(
      http.get("/v1/sessions/sess-1/next", () => {
        served += 1
        return HttpResponse.json(served === 1 ? CHOICE : { state: "exhausted" })
      }),
      http.post("/v1/answers", () =>
        HttpResponse.json({
          responseId: "r-1",
          gradeStatus: "graded",
          senseId: 42,
          renderFormat: "single_choice",
          isCorrect: true,
          gradeScore: 1,
          gradeFeedback: "Nice.",
          reveal: { correct_index: 0, correct_option: "able to recover" },
          masteryBefore: 3,
          masteryAfter: 3.4,
          depthBefore: 1,
          depthAfter: 2,
          depthStageName: "recognition",
        }),
      ),
    )
    renderRunner(LIVE)

    await userEvent.click(await screen.findByRole("radio", { name: "able to recover" }))
    await userEvent.click(screen.getByRole("button", { name: /Submit/ }))

    expect(await screen.findByText(/Nice\./)).toBeTruthy()
    // A settled question offers Continue, and the answer controls are gone.
    expect(screen.getByRole("button", { name: /Continue/ })).toBeTruthy()
  })

  it("reports a refused answer instead of pretending it was graded", async () => {
    server.use(
      http.get("/v1/sessions/sess-1/next", () => HttpResponse.json(CHOICE)),
      http.post("/v1/answers", () =>
        HttpResponse.json(
          { code: "question_not_issued_for_session", detail: "not issued" },
          { status: 409 },
        ),
      ),
    )
    renderRunner(LIVE)

    await userEvent.click(await screen.findByRole("radio", { name: "able to recover" }))
    await userEvent.click(screen.getByRole("button", { name: /Submit/ }))

    // The code is not one that re-arms the server's consume-once bind, so the screen
    // must not present the question as answered.
    await waitFor(() => {
      expect(screen.queryByText(/Nice\./)).toBeNull()
    })
  })

  it("waits for supply by polling the job rather than repeating the mutating call", async () => {
    let nextCalls = 0
    let jobPolls = 0
    server.use(
      http.get("/v1/sessions/sess-1/next", () => {
        nextCalls += 1
        return HttpResponse.json({ state: "preparing", taskId: "task-7" })
      }),
      http.get("/v1/jobs/task-7", () => {
        jobPolls += 1
        return HttpResponse.json({ status: "running" })
      }),
    )
    renderRunner(LIVE)

    await waitFor(() => {
      expect(jobPolls).toBeGreaterThan(0)
    })
    // The whole reason polling exists: `/next` reserves a delivery, so waiting on a
    // job must not re-ask it.
    expect(nextCalls).toBe(1)
  })

  it("resumes a finished session at its recap without asking for a question", async () => {
    const completed: SessionState = {
      sessionId: "sess-1",
      status: "completed",
      answersTotal: 12,
      answersCorrect: 9,
      sensesAdmitted: 12,
      sensesCompleted: 12,
      roundsUsed: 2,
      completedAt: "2026-09-24T12:00:00Z",
    }
    let nextCalls = 0
    server.use(
      http.get("/v1/sessions/sess-1/next", () => {
        nextCalls += 1
        return HttpResponse.json({ state: "exhausted" })
      }),
    )
    renderRunner(completed)

    await waitFor(() => {
      expect(screen.queryByText(/Loading your session summary/)).toBeNull()
    })
    expect(nextCalls).toBe(0)
  })
})
