import * as React from "react"

/** Matches the `md` breakpoint: below this the design spec is single-column. */
const MOBILE_BREAKPOINT = 768

const QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(QUERY)
  query.addEventListener("change", onChange)
  return () => query.removeEventListener("change", onChange)
}

function getSnapshot(): boolean {
  return window.matchMedia(QUERY).matches
}

/**
 * The server has no viewport, so it reports desktop. React swaps to the real
 * value straight after hydration without a mismatch warning, which is why this
 * is safe here and a `useEffect` + `setState` pair is not.
 */
function getServerSnapshot(): boolean {
  return false
}

/**
 * Whether the viewport is narrower than the `md` breakpoint.
 *
 * Reserved for decisions CSS genuinely cannot make — currently choosing between
 * a `Drawer` and a `Popover`, or a `Sheet` and a `Dialog`, both of which render
 * through a portal that a `lg:hidden` wrapper would not contain. Anything that
 * can be a responsive class must be one: this hook returns the desktop value on
 * the server, so using it for layout would flip the layout after hydration.
 */
export function useIsMobile(): boolean {
  return React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}
