import { createStore } from "zustand/vanilla"

import type { JobSnapshot } from "@/lib/api/resources/jobs"

/**
 * What kind of work a task represents, which decides how a settled snapshot is
 * presented and where the learner is sent afterwards.
 */
export type ActivityKind = "word-generation" | "question-generation" | "grade"

export interface ActivityTask {
  taskId: string
  kind: ActivityKind
  /** Present for grades and question generation; absent for word generation. */
  senseId: number | null
  /** The query that started a word generation, so the row can name itself. */
  label: string | null
  status: JobSnapshot["status"] | "unknown"
  errorCode: string | null
  /**
   * True when the last poll for this task failed. Polling continues with backoff and
   * the next successful snapshot clears it, so this marks a transient gap rather than
   * a settled state.
   */
  stale: boolean
}

export interface ActivityState {
  tasks: ActivityTask[]
  register: (task: {
    taskId: string
    kind: ActivityKind
    senseId?: number | null
    label?: string | null
  }) => void
  applySnapshot: (snapshot: JobSnapshot) => void
  markStale: (taskId: string) => void
  dismiss: (taskId: string) => void
  hydrate: () => void
}

export type ActivityStore = ReturnType<typeof createActivityStore>

const STORAGE_KEY = "pycil.activity.outstanding"

/** Terminal statuses. Only unsettled work needs to survive a reload. */
const SETTLED: ReadonlySet<string> = new Set(["done", "failed", "expired"])

/**
 * How far along a job is, which is all the ordering a receipt needs.
 *
 * A job's status only ever moves forward and a terminal one is final, so a snapshot
 * that ranks at or below the status already held carries no new information and is
 * dropped. That is what stops a slow poll response from resurrecting `running` after
 * `done` — a real reordering, since each poll is its own request.
 */
const STATUS_ORDER: Record<string, number> = {
  unknown: 0,
  queued: 1,
  running: 2,
  done: 3,
  failed: 3,
  expired: 3,
}

export function isUnsettled(task: ActivityTask): boolean {
  return !SETTLED.has(task.status)
}

/**
 * Only the identity of unsettled work is persisted, never a snapshot payload.
 * On the next mount the ids are re-polled and the server returns the authoritative
 * snapshot, so a stored status could only ever go stale.
 */
function persist(tasks: ActivityTask[]) {
  if (typeof window === "undefined") return
  const outstanding = tasks.filter(isUnsettled).map((task) => ({
    taskId: task.taskId,
    kind: task.kind,
    senseId: task.senseId,
    label: task.label,
  }))
  try {
    if (outstanding.length === 0) {
      window.sessionStorage.removeItem(STORAGE_KEY)
      return
    }
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(outstanding))
  } catch {
    // A full or blocked sessionStorage costs durability, not correctness.
  }
}

function readPersisted(): ActivityTask[] {
  if (typeof window === "undefined") return []
  let raw: string | null = null
  try {
    raw = window.sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return []
  }
  if (!raw) return []
  try {
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.flatMap((entry): ActivityTask[] => {
      if (!entry || typeof entry !== "object") return []
      const record = entry as Record<string, unknown>
      if (typeof record.taskId !== "string") return []
      return [
        {
          taskId: record.taskId,
          kind: (record.kind as ActivityKind) ?? "word-generation",
          senseId: typeof record.senseId === "number" ? record.senseId : null,
          label: typeof record.label === "string" ? record.label : null,
          status: "unknown",
          errorCode: null,
          stale: false,
        },
      ]
    })
  } catch {
    return []
  }
}

export function createActivityStore() {
  return createStore<ActivityState>()((set, get) => ({
    tasks: [],

    hydrate: () => {
      const restored = readPersisted()
      if (restored.length === 0) return
      set((state) => {
        const known = new Set(state.tasks.map((task) => task.taskId))
        return { tasks: [...state.tasks, ...restored.filter((t) => !known.has(t.taskId))] }
      })
    },

    register: ({ taskId, kind, senseId = null, label = null }) => {
      set((state) => {
        if (state.tasks.some((task) => task.taskId === taskId)) return state
        return {
          tasks: [
            ...state.tasks,
            {
              taskId,
              kind,
              senseId,
              label,
              status: "unknown" as const,
              errorCode: null,
              stale: false,
            },
          ],
        }
      })
      persist(get().tasks)
    },

    applySnapshot: (snapshot) => {
      set((state) => ({
        tasks: state.tasks.map((task) => {
          if (task.taskId !== snapshot.jobId) return task
          if (STATUS_ORDER[snapshot.status] <= STATUS_ORDER[task.status]) return task
          return {
            ...task,
            status: snapshot.status,
            errorCode: snapshot.errorCode,
            stale: false,
          }
        }),
      }))
      persist(get().tasks)
    },

    markStale: (taskId) => {
      set((state) => ({
        tasks: state.tasks.map((task) =>
          task.taskId === taskId ? { ...task, stale: true } : task,
        ),
      }))
    },

    dismiss: (taskId) => {
      set((state) => ({ tasks: state.tasks.filter((task) => task.taskId !== taskId) }))
      persist(get().tasks)
    },
  }))
}
