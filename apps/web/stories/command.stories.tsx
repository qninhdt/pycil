import { useState } from "react"
import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { Button } from "@/components/ui/button"
import { LiveSessionWarning } from "@/components/command/live-session-warning"
import type { LiveSession } from "@/lib/stores/ui-store"

/**
 * The palette's guard: adding a word while a session is live ends that session,
 * so the add is confirmed first.
 *
 * The dialog is driven from local state here so the interaction is real — the
 * story opens it, and confirm or cancel closes it — rather than pinning it open
 * with a prop, which would hide the open/close behaviour a review needs to see.
 */
const meta = {
  title: "Command/Live Session Warning",
  parameters: { layout: "centered" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

const liveSession: LiveSession = {
  sessionId: "session-1",
  nodeId: "node-1",
  deckTitle: "Academic Word List",
}

function Demo() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button onClick={() => setOpen(true)}>Add a word</Button>
      <LiveSessionWarning
        liveSession={liveSession}
        open={open}
        onConfirm={() => setOpen(false)}
        onCancel={() => setOpen(false)}
      />
    </>
  )
}

export const Warning: Story = {
  render: () => <Demo />,
}
