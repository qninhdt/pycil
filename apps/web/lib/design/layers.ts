/**
 * The named stacking order. Declared once so no call site reaches for an
 * arbitrary `z-50` and quietly lands above a dialog.
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

/**
 * Tailwind class for a named layer.
 *
 * Each class is a complete literal because Tailwind finds utilities by scanning
 * source text: a template built from `LAYERS[name]` is only assembled at
 * runtime, so the scanner never sees `z-[20]` and no rule is generated for it.
 *
 * The values are read from the `--z-*` custom properties in `app/globals.css`
 * rather than repeated as numbers, which is what keeps this table and the
 * stylesheet from drifting apart. `LAYERS` above stays the numeric source for
 * comparisons and for documentation.
 */
export const LAYER_CLASS: Record<LayerName, string> = {
  base: "z-[var(--z-base)]",
  stickyHeader: "z-[var(--z-header)]",
  bottomNav: "z-[var(--z-nav)]",
  drawer: "z-[var(--z-drawer)]",
  overlay: "z-[var(--z-overlay)]",
  toast: "z-[var(--z-toast)]",
}
