import type { ActionResult } from "@/lib/api/handle-api-error"
import type { LearningSettings } from "@/lib/api/types"

import { withClient } from "./authorized-action"

/**
 * The learner's session shape.
 *
 * One row per account, so there is nothing to look up first: no deck to name, no tree
 * to walk. That is the whole reason this moved off the deck — finding "your settings"
 * used to mean finding every deck you own.
 */
export async function updateLearningSettings(
  settings: LearningSettings,
): Promise<ActionResult<LearningSettings>> {
  const result = await withClient((client) =>
    client.learning.updateLearningSettings(settings),
  )
  // The saved values are read back by the settings page on its next render, so the
  // cached render has to go. Nothing else displays them: a live session carries the
  // plan it was created with, and the study screen never re-reads this.
  return result
}
