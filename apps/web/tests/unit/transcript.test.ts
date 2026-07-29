import { describe, expect, it } from "vitest"

import type { RunEvent, RunEventType } from "@/lib/api/types"
import { buildTranscript } from "@/lib/assistant/transcript"
import type { AssistantTurn } from "@/lib/assistant/transcript"

/**
 * The fold from the flat event list to renderable turns.
 *
 * These are the assertions that would have caught the four defects the last
 * revision shipped: tokens concatenated as `[object Object]`, a per-run sequence
 * colliding across runs, an approval that locked the composer forever, and a
 * recovery path with no run id to recover.
 */

/** A minimal event, with the run id defaulting to a single run for brevity. */
function ev<K extends RunEventType>(
  runId: string,
  sequence: number,
  eventType: K,
  payload: unknown,
): RunEvent {
  return { id: `${runId}-${sequence}`, runId, sequence, eventType, payload } as RunEvent
}

describe("buildTranscript", () => {
  it("is empty for no events", () => {
    const t = buildTranscript([])
    expect(t.turns).toEqual([])
    expect(t.activeRunId).toBeNull()
    expect(t.awaitingApproval).toBeNull()
  })

  it("concatenates token payloads by their `content`, not the object", () => {
    // The bug this guards: `token` payload is `{content}`, not a bare string.
    // Appending the object rendered `[object Object]` on every token.
    const t = buildTranscript([
      ev("r1", 1, "user_message", { content: "hi" }),
      ev("r1", 2, "token", { content: "one " }),
      ev("r1", 3, "token", { content: "two" }),
      ev("r1", 4, "done", {}),
    ])

    const assistant = t.turns.find((turn) => turn.kind === "assistant") as AssistantTurn
    expect(assistant.content).toBe("one two")
    expect(assistant.streaming).toBe(false)
  })

  it("keeps a streaming assistant turn open until a terminal event", () => {
    const t = buildTranscript([
      ev("r1", 1, "token", { content: "partial" }),
    ])
    const assistant = t.turns.find((turn) => turn.kind === "assistant") as AssistantTurn
    expect(assistant.streaming).toBe(true)
  })

  it("does not collide events across runs sharing a sequence number", () => {
    // The catastrophic one: sequence is `run.event_cursor`, per-run, so every turn
    // restarts at 1. Keying dedupe on sequence alone dropped run 2's events as
    // duplicates of run 1's, silently losing most of a multi-turn thread.
    const t = buildTranscript([
      ev("r1", 1, "user_message", { content: "first question" }),
      ev("r1", 2, "token", { content: "first answer" }),
      ev("r1", 3, "done", {}),
      ev("r2", 1, "user_message", { content: "second question" }),
      ev("r2", 2, "token", { content: "second answer" }),
      ev("r2", 3, "done", {}),
    ])

    const users = t.turns.filter((turn) => turn.kind === "user")
    expect(users.map((u) => (u.kind === "user" ? u.content : ""))).toEqual([
      "first question",
      "second question",
    ])
    const assistants = t.turns.filter((turn) => turn.kind === "assistant")
    expect(assistants).toHaveLength(2)
    expect(t.activeRunId).toBe("r2")
  })

  it("de-duplicates a replayed overlap without doubling text", () => {
    // A replay re-sends events the client already holds; applying a token twice
    // would double the visible text.
    const t = buildTranscript([
      ev("r1", 1, "token", { content: "abc" }),
      ev("r1", 1, "token", { content: "abc" }),
      ev("r1", 2, "done", {}),
    ])
    const assistant = t.turns.find((turn) => turn.kind === "assistant") as AssistantTurn
    expect(assistant.content).toBe("abc")
  })

  it("orders runs by first appearance, then by sequence within a run", () => {
    // Runs are ordered by when they first appear, not by run id — a UUID-shaped id
    // must never sort a chronologically-later run ahead of an earlier one. Here
    // `zzz` appears first in the list, so it leads despite sorting last lexically;
    // and within each run the out-of-order sequence 2-before-1 is corrected.
    const t = buildTranscript([
      ev("zzz", 2, "token", { content: "B" }),
      ev("aaa", 2, "token", { content: "A" }),
      ev("aaa", 1, "user_message", { content: "second run" }),
      ev("zzz", 1, "user_message", { content: "first run" }),
    ])
    expect(t.turns.map((turn) => turn.key.charAt(0))).toEqual(["u", "a", "u", "a"])
    const [firstUser] = t.turns
    expect(firstUser.kind === "user" && firstUser.content).toBe("first run")
  })

  it("holds the pause open only while the approval is the last event", () => {
    const paused = buildTranscript([
      ev("r1", 1, "user_message", { content: "delete it" }),
      ev("r1", 2, "confirmation_required", {
        action_id: "a1",
        tool: "delete_node",
        expires_at: "2099-01-01T00:00:00Z",
        targets: { node_id: "French verbs" },
      }),
    ])
    expect(paused.awaitingApproval).not.toBeNull()
    expect(paused.awaitingApproval?.tool).toBe("delete_node")
    expect(paused.awaitingApproval?.targets.node_id).toBe("French verbs")
  })

  it("releases the pause once the decision's continuation arrives", () => {
    // The composer-lock bug: `awaitingApproval` was set and never cleared, so once
    // any approval appeared the composer stayed disabled for the thread's life. The
    // decision emits no "resolved" event — the continuation stream *is* the signal.
    const resumed = buildTranscript([
      ev("r1", 1, "user_message", { content: "delete it" }),
      ev("r1", 2, "confirmation_required", {
        action_id: "a1",
        tool: "delete_node",
        expires_at: "2099-01-01T00:00:00Z",
        targets: {},
      }),
      ev("r1", 3, "token", { content: "Done." }),
      ev("r1", 4, "done", {}),
    ])
    expect(resumed.awaitingApproval).toBeNull()
  })

  it("carries an approval's own run id so its continuation groups with it", () => {
    const t = buildTranscript([
      ev("run-abc", 5, "confirmation_required", {
        action_id: "a1",
        tool: "publish_node",
        expires_at: "2099-01-01T00:00:00Z",
        targets: {},
      }),
    ])
    expect(t.awaitingApproval?.runId).toBe("run-abc")
  })

  it("matches a tool result to its pending call by tool name", () => {
    const t = buildTranscript([
      ev("r1", 1, "tool_call", { tool: "search_word" }),
      ev("r1", 2, "tool_result", { tool: "search_word", content: "3 results" }),
    ])
    const tool = t.turns.find((turn) => turn.kind === "tool")
    expect(tool?.kind === "tool" && tool.result).toBe("3 results")
  })

  it("surfaces a run error as its own turn with the server's code", () => {
    const t = buildTranscript([
      ev("r1", 1, "token", { content: "working" }),
      ev("r1", 2, "error", { code: "deadline_exceeded" }),
    ])
    const error = t.turns.find((turn) => turn.kind === "error")
    expect(error?.kind === "error" && error.code).toBe("deadline_exceeded")
  })
})
