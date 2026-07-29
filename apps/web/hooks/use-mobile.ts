import * as React from "react"

/**
 * Viewport queries for the two decisions CSS genuinely cannot make.
 *
 * Anything expressible as a responsive class must be one. These hooks exist only
 * for choosing between two *different components* — a `Drawer` versus a `Popover`,
 * a portal versus an in-flow element — where a `lg:hidden` wrapper cannot help
 * because the portal escapes it and renders anyway.
 */

/** The `md` breakpoint: below this the design spec is single-column. */
const MOBILE_BREAKPOINT = 768

/** The `lg` breakpoint, where the shell swaps the tab bar for the nav rail. */
const DESKTOP_BREAKPOINT = 1024

function useMediaQuery(query: string): boolean {
  const subscribe = React.useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia(query)
      list.addEventListener("change", onChange)
      return () => list.removeEventListener("change", onChange)
    },
    [query],
  )

  const getSnapshot = React.useCallback(() => window.matchMedia(query).matches, [query])

  // The server has no viewport, so every query reports false and the server renders
  // the desktop case. React swaps to the real value straight after hydration without
  // a mismatch warning, which is why this is safe and a `useEffect` + `setState` pair
  // is not.
  const getServerSnapshot = React.useCallback(() => false, [])

  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}

/**
 * Whether the viewport is narrower than `md`.
 *
 * Used where the mobile form is a bottom sheet and the desktop form is a popover
 * anchored to its trigger — the activity centre being the current case.
 */
export function useIsMobile(): boolean {
  return useMediaQuery(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
}

/**
 * Whether the viewport is narrower than `lg`, which is where the shell changes shape.
 *
 * Distinct from `useIsMobile` on purpose. The assistant's desktop form is an in-flow
 * sidebar that shrinks the content column, and the column only has room for one once
 * the nav rail has replaced the bottom tab bar. Keying it to `md` instead put a
 * full-height sidebar and the bottom tab bar on screen together between 768 and
 * 1023px, where they overlap.
 */
export function useIsBelowDesktop(): boolean {
  return useMediaQuery(`(max-width: ${DESKTOP_BREAKPOINT - 1}px)`)
}
