import { createStore } from "zustand/vanilla"

import type { ModelCatalog, Thread } from "@/lib/api/types"

export interface AssistantState {
  threads: Thread[]
  listRead: boolean
  listProblem: string | null
  openThreadId: string | null
  listLoaded: boolean
  /** The server's model allowlist, or null before it has been read. */
  catalog: ModelCatalog | null
  /**
   * The model and effort the next turn will use.
   *
   * Held here rather than in a component because the assistant surface has two
   * mutually exclusive renderings: crossing the desktop breakpoint unmounts one
   * and mounts the other, so a selection kept in either would be lost mid-session.
   */
  selectedModel: string | null
  selectedEffort: string | null
  openThread: (threadId: string | null) => void
  setThreads: (threads: Thread[], problem: string | null, read?: boolean) => void
  setListLoaded: (loaded: boolean) => void
  setCatalog: (catalog: ModelCatalog) => void
  selectModel: (modelId: string) => void
  selectEffort: (effort: string) => void
}

export type AssistantStore = ReturnType<typeof createAssistantStore>

export function createAssistantStore() {
  return createStore<AssistantState>()((set, get) => ({
    threads: [],
    listRead: false,
    listProblem: null,
    openThreadId: null,
    listLoaded: false,
    catalog: null,
    selectedModel: null,
    selectedEffort: null,
    openThread: (openThreadId) => set({ openThreadId }),
    setThreads: (threads, listProblem, read = true) =>
      set((state) => ({
        threads,
        listProblem,
        listRead: state.listRead || read,
        openThreadId: read && state.openThreadId && !threads.some((thread) => thread.id === state.openThreadId)
          ? null
          : state.openThreadId,
      })),
    setListLoaded: (listLoaded) => set({ listLoaded }),
    setCatalog: (catalog) =>
      set({
        catalog,
        selectedModel: catalog.defaultModel,
        selectedEffort: catalog.defaultReasoningEffort,
      }),
    selectModel: (modelId) => {
      const { catalog } = get()
      const model = catalog?.models.find((entry) => entry.id === modelId)
      if (!model) return
      const effort = get().selectedEffort
      // An effort the new model does not support would be refused by the server,
      // so it is coerced to the model's own first choice rather than carried over.
      set({
        selectedModel: modelId,
        selectedEffort: effort && model.supportedEfforts.includes(effort)
          ? effort
          : model.supportedEfforts[0] ?? "none",
      })
    },
    selectEffort: (selectedEffort) => set({ selectedEffort }),
  }))
}
