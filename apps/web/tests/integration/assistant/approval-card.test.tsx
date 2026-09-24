import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import {
  ApprovalRequestCard,
  type ApprovalRequest,
} from "@/components/assistant/approval-request-card"

/**
 * The approval gate, rendered as the learner sees it.
 *
 * This is the last screen between a model's suggestion and a deleted deck, so the
 * assertions are about what a person can actually read and press: that the target is
 * named, that the destructive framing is on the approve control rather than the safe
 * one, and that nothing is decided without a click.
 */

function approval(overrides: Partial<ApprovalRequest> = {}): ApprovalRequest {
  return {
    key: "k1",
    runId: "run-1",
    actionId: "call-1",
    tool: "delete_node",
    targets: { node_id: "IELTS Vocabulary" },
    ...overrides,
  }
}

describe("an approval request for a destructive tool", () => {
  it("names what will be deleted rather than saying 'this item'", () => {
    render(<ApprovalRequestCard approval={approval()} onDecide={vi.fn()} />)

    expect(screen.getByText("IELTS Vocabulary")).toBeTruthy()
    expect(screen.getByText(/permanently delete this and everything inside it/)).toBeTruthy()
  })

  it("frames the destructive action on the approve control", () => {
    render(<ApprovalRequestCard approval={approval()} onDecide={vi.fn()} />)

    // A learner skimming two buttons must not read the irreversible one as the
    // default. Both the label and the variant say so.
    expect(screen.getByRole("button", { name: "Approve anyway" })).toBeTruthy()
    expect(screen.getByRole("button", { name: "Reject" })).toBeTruthy()
  })

  it("does not decide anything on its own", () => {
    const onDecide = vi.fn()
    render(<ApprovalRequestCard approval={approval()} onDecide={onDecide} />)

    expect(onDecide).not.toHaveBeenCalled()
  })

  it("sends the decision the server accepts, with the interrupt's own identifiers", async () => {
    const onDecide = vi.fn().mockResolvedValue(undefined)
    render(<ApprovalRequestCard approval={approval()} onDecide={onDecide} />)

    await userEvent.click(screen.getByRole("button", { name: "Approve anyway" }))

    expect(onDecide).toHaveBeenCalledWith("run-1", "call-1", "approve")
  })

  it("reports a rejection as a rejection", async () => {
    const onDecide = vi.fn().mockResolvedValue(undefined)
    render(<ApprovalRequestCard approval={approval()} onDecide={onDecide} />)

    await userEvent.click(screen.getByRole("button", { name: "Reject" }))

    expect(onDecide).toHaveBeenCalledWith("run-1", "call-1", "reject")
  })

  it("keeps the decision available when the request fails", async () => {
    // The chat surface reports the transport error. What matters here is that a
    // failed decision does not silently consume the only chance to answer.
    const onDecide = vi.fn().mockRejectedValue(new Error("network"))
    render(<ApprovalRequestCard approval={approval()} onDecide={onDecide} />)

    await userEvent.click(screen.getByRole("button", { name: "Reject" }))

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Reject" })).toHaveProperty("disabled", false)
    })
  })

  it("says so rather than guessing when the target cannot be resolved", () => {
    render(<ApprovalRequestCard approval={approval({ targets: {} })} onDecide={vi.fn()} />)

    expect(screen.getByText(/could not be confirmed/)).toBeTruthy()
  })
})

describe("an approval request for a reversible tool", () => {
  it("reads as an ordinary confirmation", () => {
    render(
      <ApprovalRequestCard
        approval={approval({ tool: "move_node", targets: { node_id: "Phrasal Verbs" } })}
        onDecide={vi.fn()}
      />,
    )

    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy()
    expect(screen.getByText(/move this into another folder/)).toBeTruthy()
  })
})
