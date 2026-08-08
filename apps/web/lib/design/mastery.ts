/**
 * Resolving a mastery score to its band.
 *
 * The band table itself is generated from the API's learning policy into
 * `mastery.generated.ts` — it is a cross-language contract, and it used to be
 * mirrored here by hand with only a comment asking future editors to keep the two
 * in step. Both render on the same screens (a deck row shows the server's
 * `masteryStageName` while the dashboard and study verdict resolve the name here),
 * so a drifting edge showed one learner two labels for one score.
 *
 * The functions stay hand-written and stay tested: clamping, rounding and NaN
 * handling are frontend display decisions, not part of the contract.
 */

export type { MasteryBand, MasteryStage } from "./mastery.generated"
export {
  MASTERED_FLOOR,
  MASTERY_BANDS,
} from "./mastery.generated"

import { MASTERY_BANDS, type MasteryBand } from "./mastery.generated"

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
