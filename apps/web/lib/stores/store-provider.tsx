"use client"

import { createContext, useContext, useEffect, useState } from "react"
import { useStore } from "zustand"

import { createActivityStore, type ActivityState, type ActivityStore } from "./activity-store"
import { createUiStore, type UiState, type UiStore } from "./ui-store"

/**
 * Both stores are created once per provider mount. The provider is mounted in
 * the root layout only: a second mount anywhere would fork every store, so the
 * command palette could register a task the study screen never sees.
 */
const ActivityStoreContext = createContext<ActivityStore | null>(null)
const UiStoreContext = createContext<UiStore | null>(null)

export function StoreProvider({ children }: { children: React.ReactNode }) {
  // A lazy initializer rather than a ref: both run the factory once per mount,
  // but a ref's `current` is not a render-time value, and reading one to build
  // the context value is exactly the pattern that silently fails to update.
  const [activityStore] = useState(createActivityStore)
  const [uiStore] = useState(createUiStore)

  // Outstanding task ids are read back after mount, not during render: the
  // server has no sessionStorage, so hydrating in the initial state would make
  // the first client render disagree with the server markup.
  useEffect(() => {
    activityStore.getState().hydrate()
  }, [activityStore])

  return (
    <ActivityStoreContext.Provider value={activityStore}>
      <UiStoreContext.Provider value={uiStore}>{children}</UiStoreContext.Provider>
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

export function useUiStore<T>(selector: (state: UiState) => T): T {
  const store = useContext(UiStoreContext)
  if (!store) throw new Error("useUiStore must be used inside StoreProvider")
  return useStore(store, selector)
}
