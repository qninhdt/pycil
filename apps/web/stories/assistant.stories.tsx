import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { ApprovalRequestCard } from "@/components/assistant/approval-request-card"
import { RunRecoveryNotice } from "@/components/assistant/run-recovery-notice"
import type { ApprovalTurn } from "@/lib/assistant/transcript"

/**
 * The two assistant surfaces that gate on a human: the approval card the run
 * pauses on, and the recovery notice shown when a stream drops mid-reply.
 *
 * The approval card's whole job is to name what is about to happen before it
 * does, so the variants pin the cases that matter: a reversible move, an
 * irreversible delete, a target the server could not name, and an expired
 * request whose approve button is gone but whose reject remains.
 */
const meta = {
  title: "Assistant/Confirmation",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

/** An hour out, so the countdown renders live rather than expired. */
const future = new Date(Date.now() + 60 * 60 * 1000).toISOString()
const past = new Date(Date.now() - 60 * 1000).toISOString()

function approval(overrides: Partial<ApprovalTurn> = {}): ApprovalTurn {
  return {
    kind: "approval",
    key: "approval-1",
    runId: "run-1",
    actionId: "action-1",
    tool: "move_node",
    expiresAt: future,
    targets: { node_id: "Academic Word List" },
    ...overrides,
  }
}

export const ReversibleMove: Story = {
  render: () => (
    <div className="max-w-md">
      <ApprovalRequestCard approval={approval()} onDecide={() => {}} />
    </div>
  ),
}

export const IrreversibleDelete: Story = {
  render: () => (
    <div className="max-w-md">
      <ApprovalRequestCard
        approval={approval({
          tool: "delete_node",
          targets: { node_id: "IELTS preparation" },
        })}
        onDecide={() => {}}
      />
    </div>
  ),
}

/** No nameable target: the card refuses to imply one and says so. */
export const UnnamedTarget: Story = {
  render: () => (
    <div className="max-w-md">
      <ApprovalRequestCard
        approval={approval({ tool: "publish_node", targets: {} })}
        onDecide={() => {}}
      />
    </div>
  ),
}

/** Past the deadline: approve is disabled, reject stays so it can be dismissed. */
export const Expired: Story = {
  render: () => (
    <div className="max-w-md">
      <ApprovalRequestCard
        approval={approval({ tool: "delete_node", expiresAt: past })}
        onDecide={() => {}}
      />
    </div>
  ),
}

/** The turn is resolving; both controls lock while the decision posts. */
export const Deciding: Story = {
  render: () => (
    <div className="max-w-md">
      <ApprovalRequestCard approval={approval()} onDecide={() => {}} disabled />
    </div>
  ),
}

/**
 * A dropped stream with a known run id offers both truthful choices: re-read
 * what the server persisted, or send the turn again.
 */
export const RecoveryWithReplay: Story = {
  render: () => (
    <div className="max-w-md">
      <RunRecoveryNotice onReplay={() => {}} onResend={() => {}} busy={false} />
    </div>
  ),
}

/** No run id known yet, so only the resend offer is truthful. */
export const RecoveryResendOnly: Story = {
  render: () => (
    <div className="max-w-md">
      <RunRecoveryNotice onResend={() => {}} busy={false} />
    </div>
  ),
}
