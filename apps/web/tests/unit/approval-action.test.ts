import { describe, expect, test } from "vitest"

import { approvalAction } from "@/lib/assistant/approval-action"

/**
 * A live stream nests the approval request under the adapter's metadata envelope;
 * a persisted thread read has it at the top level. Reading only one shape is how
 * the card ends up labelling a delete as "an action" against no target.
 */
describe("approvalAction", () => {
  test("reads a live stream interrupt from the adapter envelope", () => {
    const interrupt = {
      id: "interrupt-1",
      reason: "langgraph:interrupt",
      metadata: {
        langgraph: {
          raw: {
            action_requests: [
              {
                name: "delete_node",
                args: { node_id: "node-abc" },
                toolCallId: "call-1",
                description: "...",
              },
            ],
            review_configs: [{ action_name: "delete_node", allowed_decisions: ["approve", "reject"] }],
          },
        },
      },
    }

    expect(approvalAction(interrupt as never)).toEqual({
      tool: "delete_node",
      targets: { node_id: "node-abc" },
      toolCallId: "call-1",
    })
  })

  test("reads a persisted thread interrupt from the top level", () => {
    const interrupt = {
      id: "interrupt-2",
      action_requests: [{ name: "move_node", args: { node_id: "n1", parent_id: "p1" } }],
    }

    expect(approvalAction(interrupt as never)).toEqual({
      tool: "move_node",
      targets: { node_id: "n1", parent_id: "p1" },
      toolCallId: null,
    })
  })

  test("falls back to a neutral label rather than inventing a tool", () => {
    expect(approvalAction({ id: "interrupt-3" } as never)).toEqual({
      tool: "action",
      targets: {},
      toolCallId: null,
    })
  })

  test("drops non-string arguments instead of stringifying them", () => {
    const interrupt = {
      id: "interrupt-4",
      action_requests: [
        { name: "remove_senses_from_deck", args: { deck_id: "d1", sense_ids: [1, 2, 3] } },
      ],
    }

    expect(approvalAction(interrupt as never).targets).toEqual({ deck_id: "d1" })
  })
})
