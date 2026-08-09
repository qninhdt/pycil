/**
 * Generated from apps/api/pycil/policy/policy.py by scripts/extract-realtime-contracts.py. Do not edit.
 *
 * Source fingerprint: e07921786315
 *
 * The mastery bands and their learner-visible names.
 *
 * Bounds are inclusive on both ends and tile 0..100 with no gap, which the
 * generator verifies before writing: `masteryBand()` falls back to the last
 * band when its lookup misses, so a gap would silently render as the top
 * stage rather than as an error.
 *
 * The band-resolving functions live in `mastery.ts` and stay hand-written.
 * The numbers are the cross-language contract; the lookup logic is not.
 *
 * Regenerate with:  python3 scripts/extract-realtime-contracts.py
 */

export type MasteryStage = 1 | 2 | 3 | 4 | 5

export interface MasteryBand {
  stage: MasteryStage
  name: string
  /** Inclusive lower bound of the mastery score. */
  min: number
  /** Inclusive upper bound of the mastery score. */
  max: number
}

export const MASTERY_BANDS: readonly MasteryBand[] = [
  { stage: 1, name: "New", min: 0, max: 10 },
  { stage: 2, name: "Recognised", min: 11, max: 30 },
  { stage: 3, name: "Familiar", min: 31, max: 55 },
  { stage: 4, name: "Applied", min: 56, max: 80 },
  { stage: 5, name: "Fluent", min: 81, max: 100 },
] as const

/**
 * The server-owned score at or above which a sense counts as mastered.
 *
 * Read from `MASTERED_FLOOR` in the policy module. This is intentionally
 * separate from the visual bands: the approved floor is 80 while Fluent
 * begins at 81.
 */
export const MASTERED_FLOOR = 80
