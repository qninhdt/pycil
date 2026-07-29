import { describe, expect, it } from "vitest"

import {
  isAsyncTaskSnapshot,
  reduceAsyncTaskSnapshot,
  type AsyncTaskSnapshot,
} from "@/lib/realtime/task-snapshot"

/**
 * Snapshot reconciliation for an async task delivered over the realtime channel.
 *
 * The subscribe proxy replays the latest persisted state and then streams live
 * updates, so the same task version can arrive more than once and updates can
 * arrive out of order. Reconciliation must be monotonic — a later observation may
 * only replace an earlier one — or a reload would show a settled grade regressing
 * to `running`.
 */

function snap(overrides: Partial<AsyncTaskSnapshot> = {}): AsyncTaskSnapshot {
  return {
    schema: "async-task.v1",
    eventId: "e1",
    taskId: "t1",
    kind: "grade_answer",
    status: "running",
    version: 1,
    result: null,
    errorCode: null,
    ...overrides,
  }
}

describe("reduceAsyncTaskSnapshot", () => {
  it("takes the first valid snapshot when there is nothing yet", () => {
    const next = reduceAsyncTaskSnapshot(null, snap(), "t1")
    expect(next?.eventId).toBe("e1")
  })

  it("advances to a higher version", () => {
    const current = snap({ version: 1, status: "running" })
    const incoming = snap({ version: 2, status: "succeeded", eventId: "e2" })
    const next = reduceAsyncTaskSnapshot(current, incoming, "t1")
    expect(next?.status).toBe("succeeded")
    expect(next?.version).toBe(2)
  })

  it("ignores a lower version, so a late replay cannot regress the state", () => {
    const current = snap({ version: 5, status: "succeeded", eventId: "e5" })
    const stale = snap({ version: 2, status: "running", eventId: "e2" })
    const next = reduceAsyncTaskSnapshot(current, stale, "t1")
    expect(next?.status).toBe("succeeded")
    expect(next?.version).toBe(5)
  })

  it("ignores an equal version (a duplicate delivery)", () => {
    const current = snap({ version: 3, eventId: "e3" })
    const duplicate = snap({ version: 3, eventId: "e3-again", status: "failed" })
    const next = reduceAsyncTaskSnapshot(current, duplicate, "t1")
    // Same version: the first one wins, no flip to failed.
    expect(next?.status).toBe("running")
  })

  it("ignores a repeat of the same eventId even if the version claims to be higher", () => {
    const current = snap({ version: 1, eventId: "e1" })
    const replay = snap({ version: 9, eventId: "e1", status: "succeeded" })
    const next = reduceAsyncTaskSnapshot(current, replay, "t1")
    expect(next?.status).toBe("running")
  })

  it("drops a snapshot addressed to a different task", () => {
    const current = snap({ taskId: "t1", version: 1 })
    const other = snap({ taskId: "t2", version: 5, status: "succeeded" })
    const next = reduceAsyncTaskSnapshot(current, other, "t1")
    expect(next).toBe(current)
  })

  it("drops a snapshot whose taskId does not match the subscribed id, even from null", () => {
    const next = reduceAsyncTaskSnapshot(null, snap({ taskId: "t2" }), "t1")
    expect(next).toBeNull()
  })

  it("rejects a structurally invalid payload", () => {
    const current = snap()
    expect(reduceAsyncTaskSnapshot(current, { not: "a snapshot" }, "t1")).toBe(current)
    expect(reduceAsyncTaskSnapshot(current, null, "t1")).toBe(current)
    expect(reduceAsyncTaskSnapshot(current, "string", "t1")).toBe(current)
  })
})

describe("isAsyncTaskSnapshot", () => {
  it("accepts a well-formed snapshot", () => {
    expect(isAsyncTaskSnapshot(snap())).toBe(true)
    expect(isAsyncTaskSnapshot(snap({ status: "expired", errorCode: "grade_timeout" }))).toBe(true)
  })

  it("rejects a wrong schema tag", () => {
    expect(isAsyncTaskSnapshot(snap({ schema: "async-task.v2" as never }))).toBe(false)
  })

  it("rejects an unknown status", () => {
    expect(isAsyncTaskSnapshot(snap({ status: "cancelled" as never }))).toBe(false)
  })

  it("rejects a non-object value", () => {
    expect(isAsyncTaskSnapshot(null)).toBe(false)
    expect(isAsyncTaskSnapshot(42)).toBe(false)
    expect(isAsyncTaskSnapshot(undefined)).toBe(false)
  })
})
