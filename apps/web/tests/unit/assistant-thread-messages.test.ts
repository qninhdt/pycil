import { describe, expect, it } from "vitest"

import { threadMessages } from "@/lib/assistant/thread-messages"

describe("persisted assistant history", () => {
  it("restores inline images as private attachment previews", () => {
    const messages = threadMessages({
      status: "idle",
      messages: [{ type: "human", content: [
        { type: "text", text: "Add these words" },
        { type: "image_url", image_url: { url: "data:image/jpeg;base64,YWJj" } },
      ] }],
      interrupts: [],
    })

    expect(messages[0]).toMatchObject({
      role: "user",
      content: [{ text: "Add these words" }],
      attachments: [{ type: "image", content: [{ image: "data:image/jpeg;base64,YWJj" }] }],
    })
  })

  it("restores an interrupted action as an answerable AG-UI interrupt", () => {
    const messages = threadMessages({
      status: "interrupted",
      messages: [{ type: "human", content: "delete it" }],
      interrupts: [{
        id: "interrupt-1",
        action_requests: [{ name: "delete_node", toolCallId: "call-1", args: { node_id: "Deck" } }],
      }],
    })

    expect(messages[0]).toMatchObject({ role: "user", content: [{ text: "delete it" }] })
    expect(messages.at(-1)).toMatchObject({
      role: "assistant",
      status: { type: "requires-action", reason: "interrupt" },
      metadata: { custom: { agui: { interrupts: [{
        id: "interrupt-1",
        toolCallId: "call-1",
        metadata: { tool: "delete_node", targets: { node_id: "Deck" } },
      }] } } },
    })
  })
})
