"use client"

import { createContext, useContext, useEffect, useState } from "react"
import { useStore } from "zustand"

import { createActivityStore, type ActivityState, type ActivityStore } from "./activity-store"
import { createAssistantStore, type AssistantState, type AssistantStore } from "./assistant-store"
import { AssistantRuntimeBridge } from "@/components/assistant/assistant-runtime-bridge"
import { createUiStore, type UiState, type UiStore } from "./ui-store"

/**
 * Every store is created once per provider mount. The provider is mounted in
 * the root layout only: a second mount anywhere would fork every store, so the
 * command palette could register a task the study screen never sees.
 *
 * The assistant store is here for a sharper version of the same reason. Its two
 * surfaces are mutually exclusive by viewport, so crossing 1024px unmounts one and
 * mounts the other — state owned any lower than this would not survive that.
 */
const ActivityStoreContext = createContext<ActivityStore | null>(null)
const AssistantStoreContext = createContext<AssistantStore | null>(null)
const UiStoreContext = createContext<UiStore | null>(null)

export function StoreProvider({ children }: { children: React.ReactNode }) {
  // A lazy initializer rather than a ref: both run the factory once per mount,
  // but a ref's `current` is not a render-time value, and reading one to build
  // the context value is exactly the pattern that silently fails to update.
  const [activityStore] = useState(createActivityStore)
  const [assistantStore] = useState(createAssistantStore)
  const [uiStore] = useState(createUiStore)

  // Outstanding task ids are read back after mount, not during render: the
  // server has no sessionStorage, so hydrating in the initial state would make
  // the first client render disagree with the server markup.
  useEffect(() => {
    activityStore.getState().hydrate()
  }, [activityStore])

  return (
    <ActivityStoreContext.Provider value={activityStore}>
      <AssistantStoreContext.Provider value={assistantStore}>
        <AssistantRuntimeBridge store={assistantStore}>
          <UiStoreContext.Provider value={uiStore}>{children}</UiStoreContext.Provider>
        </AssistantRuntimeBridge>
      </AssistantStoreContext.Provider>
    </ActivityStoreContext.Provider>
  )
}

/**
 * Throwing beats returning a default store: a silent fallback would be a second
 * instance, which is the exact failure the single mount point exists to prevent.
 */
export function useActivityStore<T>(selector: (state: ActivityState) => T): T {
  const store = useContext(ActivityStoreContext)
  if (!store) throw new Error("useActivityStore must be used inside StoreProvider")
  return useStore(store, selector)
}

export function useActivityActions() {
  const store = useContext(ActivityStoreContext)
  if (!store) throw new Error("useActivityActions must be used inside StoreProvider")
  return store.getState()
}

export function useAssistantStore<T>(selector: (state: AssistantState) => T): T {
  const store = useContext(AssistantStoreContext)
  if (!store) throw new Error("useAssistantStore must be used inside StoreProvider")
  return useStore(store, selector)
}

/**
 * The assistant store itself, for the hook that drives the conversation.
 *
 * That hook reads and mutates the transport — the open stream, the turn key — from
 * inside callbacks rather than during render, so it needs the store rather than a
 * subscription to a slice of it. Subscribing would re-run the callbacks on every
 * event that arrives, which for a streaming transcript is every frame.
 */
export function useAssistantStoreApi(): AssistantStore {
  const store = useContext(AssistantStoreContext)
  if (!store) throw new Error("useAssistantStoreApi must be used inside StoreProvider")
  return store
}

export function useUiStore<T>(selector: (state: UiState) => T): T {
  const store = useContext(UiStoreContext)
  if (!store) throw new Error("useUiStore must be used inside StoreProvider")
  return useStore(store, selector)
}
