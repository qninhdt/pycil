import "server-only"

import { createApiClient } from "@/lib/api/client"
import type { LearningSettings, Viewer } from "@/lib/api/types"
import { getSession } from "@/lib/auth/session"

/**
 * The signed-in profile, read for the settings screen.
 *
 * A plain server-only function rather than a server action: nothing mutates and nothing
 * calls it from the browser, so `"use server"` would publish a callable endpoint for no
 * reason.
 *
 * Read from the API rather than from the session cookie. The cookie holds a snapshot
 * taken at sign-in, so a name or picture changed upstream since then would be stale
 * here — and this is the one screen whose entire job is to show what the account
 * currently is. The route's error boundary states a failed read; there is no useful
 * half-rendered settings page.
 */
export async function readViewer(): Promise<Viewer> {
  return createApiClient(await getSession()).auth.getViewer()
}

/**
 * The learner's effective session shape.
 *
 * Read here rather than in the form so the form has real values on its first paint: a
 * client-side fetch would render empty inputs and then fill them in, which reads as the
 * settings having been lost.
 *
 * Never empty. Someone who has never saved has no stored row, and the API resolves that
 * to the policy defaults, so this always describes what the next session will do.
 */
export async function readLearningSettings(): Promise<LearningSettings> {
  return createApiClient(await getSession()).learning.getLearningSettings()
}
