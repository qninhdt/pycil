"use server"

import { redirect } from "next/navigation"

import type { ActionResult } from "@/lib/api/handle-api-error"
import type { AccountExport } from "@/lib/api/types"
import { getSession } from "@/lib/auth/session"

import { withClient } from "./authorized-action"

/** Reading and destroying the account itself. */

/**
 * The full data export.
 *
 * Every section is an opaque snapshot rather than a typed model, because the point
 * is completeness, not a shape the UI renders. The caller offers it as a download.
 */
export async function exportAccount(): Promise<ActionResult<AccountExport>> {
  return withClient((client) => client.auth.exportAccount())
}

/**
 * Deletes the account, then destroys the local session and leaves.
 *
 * Irreversible. The API requires the refresh token so it can revoke the whole
 * token family, and a literal confirmation string which it validates itself — so a
 * wrong value is refused server-side rather than trusted from here.
 *
 * The local cookie is destroyed only after the API confirms. Destroying it first
 * would strand a live account with no way back in from this browser.
 *
 * On success this never returns: `redirect` throws, so the only value a caller can
 * observe is a failure. The return type says so rather than promising a success
 * branch that cannot arrive.
 */
export async function deleteAccount(): Promise<
  Extract<ActionResult<void>, { success: false }>
> {
  const session = await getSession()
  const refreshToken = session.refreshToken

  if (!refreshToken) {
    return {
      success: false,
      error: "Sign in again before deleting your account.",
      code: "not_authenticated",
    }
  }

  const result = await withClient((client) => client.auth.deleteAccount(refreshToken))
  if (!result.success) return result

  session.destroy()
  redirect("/login")
}
