import { useSyncExternalStore } from "react"

/** Nothing changes after hydration, so no subscriber is ever called. */
function subscribe() {
  return () => {}
}

/**
 * False during the server render and the first client render, true afterwards.
 *
 * The obvious spelling is `useState(false)` plus `useEffect(() => setTrue())`,
 * but that is a synchronous setState inside an effect: it schedules a second
 * render pass for a value that was already known. `useSyncExternalStore` takes
 * the client and server snapshots as two separate arguments, which is the same
 * answer without the extra pass.
 *
 * Use this only for genuinely client-only facts — a resolved theme, a media
 * query — never to defer content the server could have rendered.
 */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  )
}
