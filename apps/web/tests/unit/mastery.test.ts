import { describe, expect, it } from "vitest"

import {
  MASTERY_BANDS,
  MASTERY_STAGE_COUNT,
  masteryBand,
  masteryStageAttr,
  masteryStageName,
} from "@/lib/design/mastery"

/**
 * Mastery score → band mapping.
 *
 * The thresholds mirror the API's learning policy, so the risk this guards is
 * drift at the boundaries: an off-by-one at a band edge names the same score two
 * different stages on two screens. Every inclusive edge is asserted, plus the
 * clamp behaviour that keeps a bad score from blanking the ramp.
 */

describe("masteryBand", () => {
  it("has five contiguous bands covering 0-100 with no gap or overlap", () => {
    expect(MASTERY_STAGE_COUNT).toBe(5)
    expect(MASTERY_BANDS[0].min).toBe(0)
    expect(MASTERY_BANDS[MASTERY_BANDS.length - 1].max).toBe(100)
    for (let i = 1; i < MASTERY_BANDS.length; i++) {
      expect(MASTERY_BANDS[i].min).toBe(MASTERY_BANDS[i - 1].max + 1)
    }
  })

  it("resolves each band's inclusive lower and upper edge to that band", () => {
    for (const band of MASTERY_BANDS) {
      expect(masteryBand(band.min).stage).toBe(band.stage)
      expect(masteryBand(band.max).stage).toBe(band.stage)
    }
  })

  it("places the classic boundary scores in the right band", () => {
    expect(masteryBand(10).name).toBe("New")
    expect(masteryBand(11).name).toBe("Recognised")
    expect(masteryBand(30).name).toBe("Recognised")
    expect(masteryBand(31).name).toBe("Familiar")
    expect(masteryBand(55).name).toBe("Familiar")
    expect(masteryBand(56).name).toBe("Applied")
    expect(masteryBand(80).name).toBe("Applied")
    expect(masteryBand(81).name).toBe("Fluent")
  })

  it("rounds a fractional score to the nearest whole before banding", () => {
    // 10.4 rounds to 10 → New; 10.5 rounds to 11 → Recognised.
    expect(masteryBand(10.4).name).toBe("New")
    expect(masteryBand(10.5).name).toBe("Recognised")
  })

  it("clamps a score below zero to the first band rather than throwing", () => {
    expect(masteryBand(-20).stage).toBe(1)
  })

  it("clamps a score above 100 to the last band", () => {
    expect(masteryBand(999).stage).toBe(5)
  })

  it("treats a non-finite score as zero and degrades to the first band", () => {
    expect(masteryBand(Number.NaN).stage).toBe(1)
    expect(masteryBand(Number.POSITIVE_INFINITY).stage).toBe(1)
  })
})

describe("masteryStageName / masteryStageAttr", () => {
  it("returns the band name for a score", () => {
    expect(masteryStageName(0)).toBe("New")
    expect(masteryStageName(100)).toBe("Fluent")
  })

  it("returns the stage number as a string for the CSS data attribute", () => {
    expect(masteryStageAttr(0)).toBe("1")
    expect(masteryStageAttr(100)).toBe("5")
  })
})
