"use client";

import React, { createContext, useContext, useRef } from "react";
import { useStore } from "zustand";
import { createUIStore, type UIStore } from "./ui-store";

type UIStoreApi = ReturnType<typeof createUIStore>;

const UIStoreContext = createContext<UIStoreApi | undefined>(undefined);

export function UIStoreProvider({ children }: { children: React.ReactNode }) {
  const storeRef = useRef<UIStoreApi>(null);
  if (!storeRef.current) {
    storeRef.current = createUIStore();
  }

  return (
    <UIStoreContext.Provider value={storeRef.current}>
      {children}
    </UIStoreContext.Provider>
  );
}

export function useUIStore<T>(selector: (store: UIStore) => T): T {
  const ctx = useContext(UIStoreContext);
  if (!ctx) {
    throw new Error("useUIStore must be used within UIStoreProvider");
  }
  return useStore(ctx, selector);
}
