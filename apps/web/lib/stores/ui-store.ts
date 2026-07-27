import { createStore } from "zustand/vanilla"

/**
 * Which contextual surface is open. These are mutually exclusive on mobile,
 * where each one is a full-height sheet or drawer, so the store holds one
 * open surface rather than a boolean per surface.
 */
export type OpenSurface = "none" | "palette" | "activity" | "assistant"

/**
 * The study session currently open in this tab, as the rest of the app needs to
 * see it.
 *
 * This lives here because adding or removing a deck sense bumps the structural
 * generation of that node *and* of its ancestors and reverse references, and the
 * API rejects a session whose scope generation no longer matches. So the palette
 * has to know a session is live before it offers to add a word — and only the
 * study screen knows that. It publishes here; the palette reads.
 */
export interface LiveSession {
  sessionId: string
  /** The node being studied, which may be a folder above the target deck. */
  nodeId: string
  deckTitle: string
}

export interface UiState {
  openSurface: OpenSurface
  /**
   * The deck the palette should add words to. Search in this product always
   * happens in order to add a word somewhere, so the palette carries its
   * target instead of handing off to a separate "add to deck" step.
   */
  paletteTargetNodeId: string | null
  /** Null whenever no session is open in this tab. */
  liveSession: LiveSession | null
  openPalette: (targetNodeId?: string | null) => void
  openActivity: () => void
  openAssistant: () => void
  closeSurface: () => void
  toggleAssistant: () => void
  setLiveSession: (session: LiveSession | null) => void
}

export type UiStore = ReturnType<typeof createUiStore>

export function createUiStore() {
  return createStore<UiState>()((set) => ({
    openSurface: "none",
    paletteTargetNodeId: null,
    liveSession: null,
    openPalette: (targetNodeId = null) =>
      set({ openSurface: "palette", paletteTargetNodeId: targetNodeId }),
    openActivity: () => set({ openSurface: "activity" }),
    openAssistant: () => set({ openSurface: "assistant" }),
    closeSurface: () => set({ openSurface: "none" }),
    toggleAssistant: () =>
      set((state) => ({
        openSurface: state.openSurface === "assistant" ? "none" : "assistant",
      })),
    setLiveSession: (session) => set({ liveSession: session }),
  }))
}
