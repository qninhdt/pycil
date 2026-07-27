/**
 * The five mastery bands. These thresholds mirror `LEVEL_PROFILES` and
 * `mastery_band` in the API's learning policy; the UI must not invent its own
 * boundaries or a band would be named differently in two places.
 *
 * The stage names are shown to the learner verbatim.
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
  { stage: 1, name: "Introduced", min: 0, max: 10 },
  { stage: 2, name: "Recognised", min: 11, max: 30 },
  { stage: 3, name: "Recalled", min: 31, max: 55 },
  { stage: 4, name: "Applied", min: 56, max: 80 },
  { stage: 5, name: "Fluent", min: 81, max: 100 },
] as const

/** Total number of pips a mastery ramp renders. */
export const MASTERY_STAGE_COUNT = MASTERY_BANDS.length

/**
 * Resolves a raw mastery score to its band. Scores outside 0-100 clamp rather
 * than throw, because a score is display data and a bad value should degrade to
 * an end of the ramp instead of blanking the screen.
 */
export function masteryBand(mastery: number): MasteryBand {
  const score = Number.isFinite(mastery) ? Math.round(mastery) : 0
  if (score <= MASTERY_BANDS[0].max) return MASTERY_BANDS[0]
  const band = MASTERY_BANDS.find((b) => score >= b.min && score <= b.max)
  return band ?? MASTERY_BANDS[MASTERY_BANDS.length - 1]
}

export function masteryStageName(mastery: number): string {
  return masteryBand(mastery).name
}

/**
 * The `data-stage` attribute value that drives the ramp colour in CSS. Keeping
 * the colour in CSS rather than returning a hex here is what stops call sites
 * from hardcoding a palette value.
 */
export function masteryStageAttr(mastery: number): string {
  return String(masteryBand(mastery).stage)
}
