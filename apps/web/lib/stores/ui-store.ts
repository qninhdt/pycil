import { createStore } from "zustand";

export interface UIState {
  sidebarCollapsed: boolean;
  commandPaletteOpen: boolean;
}

export interface UIActions {
  toggleSidebar: () => void;
  setCommandPalette: (open: boolean) => void;
}

export type UIStore = UIState & UIActions;

export const createUIStore = (initialState?: Partial<UIState>) =>
  createStore<UIStore>()((set) => ({
    sidebarCollapsed: false,
    commandPaletteOpen: false,
    ...initialState,
    toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    setCommandPalette: (open) => set({ commandPaletteOpen: open }),
  }));
