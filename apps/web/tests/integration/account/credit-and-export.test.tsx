import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { http, HttpResponse } from "msw"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { CreditMeter } from "@/components/assistant/credit-meter"
import { DataExportCard } from "@/components/settings/data-export-card"

import { server } from "../server"

// The object-URL spies are installed once in the shared setup, so they have to be
// reset per test or "was never called" reads the previous test's call.
beforeEach(() => {
  vi.mocked(URL.createObjectURL).mockClear()
  vi.mocked(URL.revokeObjectURL).mockClear()
})

const CREDIT = {
  plan: "free",
  balance: 640,
  available: 640,
  periodStart: "2026-09-01T00:00:00Z",
  periodEnd: "2026-10-01T00:00:00Z",
  periodUsed: 360,
  periodGrant: 1000,
  topupBalance: 0,
}

/**
 * The allowance and the export, against the endpoints they read.
 *
 * Both are about a number the learner did not compute: how much is left, and what
 * the account holds. The credit meter's rule is that it shows nothing rather than a
 * zero it does not know, because "0 Credits" on a slow read reads as an exhausted
 * account.
 */
describe("the credit meter", () => {
  it("shows what is left out of the period's grant", async () => {
    server.use(http.get("/v1/me/credit", () => HttpResponse.json(CREDIT)))
    render(<CreditMeter />)

    expect(await screen.findByText("640")).toBeTruthy()
    expect(screen.getByText(/1,000 Credits/)).toBeTruthy()
  })

  it("clamps an overspent balance instead of rendering a negative allowance", async () => {
    // An admitted turn may finish past the balance. `balance` stays signed so the
    // ledger can settle it; `available` is what a learner sees.
    server.use(
      http.get("/v1/me/credit", () =>
        HttpResponse.json({ ...CREDIT, balance: -40, available: 0, periodUsed: 1040 }),
      ),
    )
    render(<CreditMeter />)

    expect(await screen.findByText("0")).toBeTruthy()
    expect(screen.queryByText("-40")).toBeNull()
  })

  it("renders nothing while the read is in flight or failed", async () => {
    server.use(
      http.get("/v1/me/credit", () =>
        HttpResponse.json({ code: "internal_error", detail: "boom" }, { status: 500 }),
      ),
    )
    const { container } = render(<CreditMeter />)

    await waitFor(() => {
      expect(container.textContent).toBe("")
    })
  })
})

describe("the data export", () => {
  it("downloads what the server returned", async () => {
    const exported = { nodes: [{ id: "n1", name: "IELTS" }], responses: [] }
    server.use(http.get("/v1/me/export", () => HttpResponse.json(exported)))
    render(<DataExportCard />)

    await userEvent.click(screen.getByRole("button", { name: /Download export/ }))

    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalled()
    })
    // The URL is revoked immediately: the payload is the largest thing on the
    // screen, and holding it for the life of the tab is the wrong default.
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test")
  })

  it("says what failed rather than offering a file that was never fetched", async () => {
    server.use(
      http.get("/v1/me/export", () =>
        HttpResponse.json({ code: "internal_error", detail: "boom" }, { status: 500 }),
      ),
    )
    render(<DataExportCard />)

    await userEvent.click(screen.getByRole("button", { name: /Download export/ }))

    await waitFor(() => {
      expect(URL.createObjectURL).not.toHaveBeenCalled()
    })
  })
})

describe("the assistant error notice", () => {
  it("says what happened in words, never the wire code", async () => {
    const { AssistantErrorNotice } = await import(
      "@/components/assistant/assistant-error-notice"
    )
    const { unmount } = render(<AssistantErrorNotice code="assistant_metering_state_invalid" />)

    expect(screen.getByText(/could not be settled/)).toBeTruthy()
    expect(screen.queryByText(/assistant_metering_state_invalid/)).toBeNull()
    unmount()

    // A code this build predates still has to say something a person can read.
    render(<AssistantErrorNotice code="a_code_from_the_future" />)
    expect(screen.getByText("Something went wrong. Try again.")).toBeTruthy()
  })

  it("offers a retry only where retrying can help", async () => {
    const { AssistantErrorNotice } = await import(
      "@/components/assistant/assistant-error-notice"
    )
    // A transient provider failure: the same request may work shortly.
    const { unmount } = render(
      <AssistantErrorNotice code="free_text_grade_timeout" onRetry={vi.fn()} />,
    )
    expect(screen.getByRole("button", { name: /Try again/ })).toBeTruthy()
    unmount()

    // The server already decided this one. A button that re-provokes it teaches
    // the learner the product is broken rather than that they hit a limit.
    render(<AssistantErrorNotice code="credit_exhausted" onRetry={vi.fn()} />)
    expect(screen.queryByRole("button", { name: /Try again/ })).toBeNull()
  })
})
