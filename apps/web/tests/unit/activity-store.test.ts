import { describe, expect, it } from "vitest"

import { createActivityStore } from "@/lib/stores/activity-store"
import type { JobSnapshot } from "@/lib/api/resources/jobs"

function snapshot(status: JobSnapshot["status"]): JobSnapshot {
  return { jobId: "job-1", kind: "word", status, result: null, errorCode: null }
}

describe("activity job snapshots", () => {
  it("accepts a terminal state after running", () => {
    const store = createActivityStore()
    store.getState().register({ taskId: "job-1", kind: "word-generation" })

    store.getState().applySnapshot(snapshot("running"))
    store.getState().applySnapshot(snapshot("done"))

    expect(store.getState().tasks[0].status).toBe("done")
  })

  it("ignores a late snapshot that would move the job backwards", () => {
    // Each poll is its own request, so a slow `running` response can land after the
    // `done` one. Rendering it would show finished work as still in progress.
    const store = createActivityStore()
    store.getState().register({ taskId: "job-1", kind: "word-generation" })

    store.getState().applySnapshot(snapshot("done"))
    store.getState().applySnapshot(snapshot("running"))

    expect(store.getState().tasks[0].status).toBe("done")
  })

  it("keeps a terminal status final against another terminal status", () => {
    const store = createActivityStore()
    store.getState().register({ taskId: "job-1", kind: "word-generation" })

    store.getState().applySnapshot({ ...snapshot("failed"), errorCode: "job_failed" })
    store.getState().applySnapshot(snapshot("done"))

    expect(store.getState().tasks[0].status).toBe("failed")
    expect(store.getState().tasks[0].errorCode).toBe("job_failed")
  })
})
