// Mock store: in-memory state mirrored to localStorage so demo mutations
// survive page refresh. Client-only (mock dispatch happens inside fetchJson,
// which is only called from "use client" hooks).

import { buildSeed } from "./seed";
import { seedIntCounter, peekInt } from "./id";
import type { MockState } from "./types";

const STORAGE_KEY = "pycil-mock-store-v1";

let state: MockState | null = null;

function persist(s: MockState): void {
  if (typeof localStorage === "undefined") return;
  try {
    s.intSeed = peekInt();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // quota / serialization errors are non-fatal for a demo store
  }
}

function load(): MockState {
  if (typeof localStorage !== "undefined") {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as MockState;
        seedIntCounter(parsed.intSeed ?? 0);
        return parsed;
      }
    } catch {
      // fall through to a fresh seed
    }
  }
  const seeded = buildSeed();
  seedIntCounter(seeded.intSeed);
  return seeded;
}

export function getState(): MockState {
  if (!state) {
    state = load();
    persist(state);
  }
  return state;
}

// Call after any mutation to flush to localStorage.
export function commit(): void {
  if (state) persist(state);
}

// Reset demo data back to the seed (used by an optional "Reset demo" affordance).
export function resetStore(): void {
  const seeded = buildSeed();
  seedIntCounter(seeded.intSeed);
  state = seeded;
  persist(seeded);
}
