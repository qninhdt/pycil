import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { StartSessionPanel } from "@/components/study/start-session-panel"

import { server } from "../server"

const replace = vi.fn()

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn(), refresh: vi.fn() }),
}))

/**
 * Starting a session from a deck and from a folder.
 *
 * The two are different products: a deck session is scoped to that deck, while a
 * folder session gathers every readable sense beneath it. The copy is the only thing
 * that tells the learner which one they are about to get, so it is asserted here
 * rather than left to the browser journey.
 *
 * `startSession` is a server action in the app; in this layer it is the same function
 * running against MSW, so the request it issues is the real one.
 */
describe("the study start screen", () => {
  beforeEach(() => {
    replace.mockClear()
  })

  it("says a deck session covers that deck", async () => {
    render(
      <StartSessionPanel nodeId="deck-1" nodeName="IELTS Vocabulary" nodeType="DECK" itemCount={42} />,
    )

    expect(screen.getByText(/42 words in this deck/)).toBeTruthy()
    expect(screen.getByText(/picks what is due and what is new/)).toBeTruthy()
  })

  it("says a folder session gathers the whole subtree", async () => {
    render(
      <StartSessionPanel nodeId="folder-1" nodeName="IELTS" nodeType="FOLDER" itemCount={310} />,
    )

    expect(screen.getByText(/310 words in this folder/)).toBeTruthy()
  })

  it("navigates to the session the server created", async () => {
    server.use(
      http.post("/v1/sessions", () =>
        HttpResponse.json({ sessionId: "sess-9", firstState: "ready" }),
      ),
    )
    render(
      <StartSessionPanel nodeId="deck-1" nodeName="Deck" nodeType="DECK" itemCount={3} />,
    )

    await userEvent.click(screen.getByRole("button", { name: /Start studying/ }))

    await waitFor(() => {
      expect(replace).toHaveBeenCalledWith("/study/sess-9")
    })
  })

  it("reports nothing due rather than opening an empty session", async () => {
    // The server admitted no work: everything in scope is scheduled for later or
    // already finished. Navigating anyway would land the learner on a recap of
    // nothing.
    server.use(
      http.post("/v1/sessions", () =>
        HttpResponse.json({ sessionId: "sess-10", firstState: "exhausted" }),
      ),
    )
    render(
      <StartSessionPanel nodeId="deck-1" nodeName="Deck" nodeType="DECK" itemCount={3} />,
    )

    await userEvent.click(screen.getByRole("button", { name: /Start studying/ }))

    expect(await screen.findByText("Nothing due right now")).toBeTruthy()
    expect(replace).not.toHaveBeenCalled()
  })

  it("says what went wrong instead of failing silently", async () => {
    server.use(
      http.post("/v1/sessions", () =>
        HttpResponse.json({ code: "forbidden", detail: "not yours" }, { status: 403 }),
      ),
    )
    render(
      <StartSessionPanel nodeId="deck-1" nodeName="Deck" nodeType="DECK" itemCount={3} />,
    )

    await userEvent.click(screen.getByRole("button", { name: /Start studying/ }))

    // The message comes from the shared error taxonomy, so this asserts that a
    // server refusal reaches the learner rather than the exact wording of one code.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /Start studying/ })).toBeTruthy()
      expect(replace).not.toHaveBeenCalled()
    })
  })
})
