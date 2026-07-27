/**
 * Motion constants. The system animates state transitions only, so the surface
 * here is deliberately small: two durations, one easing, and one entry
 * transition shared by everything that reveals content.
 *
 * Every consumer must degrade under `prefers-reduced-motion`. Components using
 * the Motion library should call `useReducedMotion()` and pass `false` as the
 * initial state; CSS-driven animation is collapsed globally in
 * `app/globals.css`.
 */

/** Standard ease-out curve. Matches the CSS `--ease-out` custom property. */
export const EASE_OUT = [0.16, 1, 0.3, 1] as const

export const DURATION = {
  /** Hover, focus, and colour changes. */
  fast: 0.12,
  /** Entry transitions and layout reveals. */
  base: 0.24,
} as const

/** Per-item delay for a staggered reveal, in seconds. */
export const STAGGER_STEP = 0.04

export interface RevealOptions {
  /** Index within a staggered group. */
  index?: number
  /** When true, all motion collapses to a static, already-revealed state. */
  reduced?: boolean
}

/**
 * The one entry transition in the system: a short rise and fade. Returns props
 * spreadable onto a `motion` element.
 */
export function reveal({ index = 0, reduced = false }: RevealOptions = {}) {
  if (reduced) {
    return {
      initial: false as const,
      animate: { opacity: 1, y: 0 },
      transition: { duration: 0 },
    }
  }
  return {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    transition: {
      duration: DURATION.base,
      delay: index * STAGGER_STEP,
      ease: EASE_OUT,
    },
  }
}
