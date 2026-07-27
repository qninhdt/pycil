/**
 * The named stacking order. Declared once so no call site reaches for an
 * arbitrary `z-50` and quietly lands above a dialog.
 *
 * These values mirror the `--z-*` custom properties in `app/globals.css`, which
 * are the same scale for use from CSS. Both must change together.
 *
 * The overlay step is 50 rather than a tidier 40 because every overlay
 * primitive in `components/ui` hardcodes `z-50`; the scale documents where they
 * already sit instead of pretending otherwise. Toast then has to clear 50.
 */
export const LAYERS = {
  base: 0,
  stickyHeader: 10,
  bottomNav: 20,
  /** Assistant drawer on mobile, assistant sidebar on desktop. */
  drawer: 30,
  /** Dialogs, sheets, popovers and the command palette. */
  overlay: 50,
  toast: 60,
} as const

export type LayerName = keyof typeof LAYERS

/** Tailwind arbitrary-value class for a named layer, e.g. `z-[10]`. */
export function layerClass(name: LayerName): string {
  return `z-[${LAYERS[name]}]`
}
