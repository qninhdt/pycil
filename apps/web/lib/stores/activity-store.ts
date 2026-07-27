import { createStore } from "zustand/vanilla"

import type { AsyncTaskSnapshot } from "@/lib/realtime/task-snapshot"

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
  status: AsyncTaskSnapshot["status"] | "unknown"
  /** Monotonic guard. A snapshot at or below this version is ignored. */
  version: number
  errorCode: string | null
  /**
   * True only when a re-subscribe was *denied*. A disconnect is not staleness:
   * the subscribe proxy replays the latest persisted snapshot and recovery is
   * enabled, so reconnecting settles the task on its own.
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
  applySnapshot: (snapshot: AsyncTaskSnapshot) => void
  markStale: (taskId: string) => void
  dismiss: (taskId: string) => void
  hydrate: () => void
}

export type ActivityStore = ReturnType<typeof createActivityStore>

const STORAGE_KEY = "pycil.activity.outstanding"

/** Terminal statuses. Only unsettled work needs to survive a reload. */
const SETTLED: ReadonlySet<string> = new Set(["succeeded", "failed", "expired"])

export function isUnsettled(task: ActivityTask): boolean {
  return !SETTLED.has(task.status)
}

/**
 * Only the identity of unsettled work is persisted, never a snapshot payload.
 * On the next mount the ids are re-subscribed and the server replays the
 * authoritative state, so a stored status could only ever go stale.
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
          version: -1,
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
              version: -1,
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
          if (task.taskId !== snapshot.taskId) return task
          // Out-of-order and replayed deliveries both arrive in practice: the
          // proxy replays the latest snapshot on every subscribe.
          if (snapshot.version <= task.version) return task
          return {
            ...task,
            status: snapshot.status,
            version: snapshot.version,
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
