import { NextRequest, NextResponse } from "next/server"
import { apiUrl } from "@/lib/api/upstream"
import { getSession } from "@/lib/auth/session"
import { RETURN_PATH_COOKIE, resolveReturnPath } from "@/lib/auth/return-path"

import type { AuthTokens, Viewer } from "@/lib/api/types"

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const code = searchParams.get("code")
  const state = searchParams.get("state")

  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"

  if (!code || !state) {
    return NextResponse.redirect(
      new URL("/login?error=invalid_callback_params", appUrl)
    )
  }

  try {
    // 1. Exchange OAuth code + state for tokens with Pycil API
    const tokenRes = await fetch(
      `${apiUrl()}/v1/auth/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`,
      { cache: "no-store" }
    )

    if (!tokenRes.ok) {
      const errText = await tokenRes.text()
      console.error(
        "Pycil API token exchange failed:",
        tokenRes.status,
        errText
      )
      return NextResponse.redirect(
        new URL("/login?error=token_exchange_failed", appUrl)
      )
    }

    // The API serializes by alias, so these arrive camelCase. This route talks
    // to the API with a raw fetch rather than the typed client, so nothing
    // converts the casing for it: reading `access_token` here yields undefined
    // and seals a session with no tokens in it.
    const tokens: AuthTokens = await tokenRes.json()
    const nowInSeconds = Math.floor(Date.now() / 1000)

    // 2. Fetch current user details from /v1/me
    const meRes = await fetch(`${apiUrl()}/v1/me`, {
      headers: {
        Authorization: `Bearer ${tokens.accessToken}`,
      },
      cache: "no-store",
    })

    if (!meRes.ok) {
      console.error(
        "Failed to fetch user profile after token exchange:",
        meRes.status
      )
      return NextResponse.redirect(
        new URL("/login?error=profile_fetch_failed", appUrl)
      )
    }

    const userProfile: Viewer = await meRes.json()

    // 3. Seal tokens and user info into iron-session cookie
    const session = await getSession()
    session.accessToken = tokens.accessToken
    session.refreshToken = tokens.refreshToken
    session.expiresAt = nowInSeconds + tokens.expiresIn
    session.refreshExpiresAt = nowInSeconds + tokens.refreshExpiresIn
    session.user = {
      id: userProfile.id,
      email: userProfile.email,
      // Both are optional on the wire and nullable in the session: an absent
      // field and an explicitly null one mean the same thing here, so the
      // distinction is collapsed rather than carried into the cookie.
      name: userProfile.name ?? null,
      image: userProfile.image ?? null,
    }
    session.isLoggedIn = true
    await session.save()

    // Back to whatever the guard interrupted, or home. The value was validated
    // before it was stored, and it is re-checked here because a cookie is not a
    // trusted channel either.
    const returnPath = resolveReturnPath(
      request.cookies.get(RETURN_PATH_COOKIE)?.value
    )
    const response = NextResponse.redirect(new URL(returnPath, appUrl))
    // One use only, so a later sign-in does not inherit this destination.
    response.cookies.delete(RETURN_PATH_COOKIE)
    return response
  } catch (error) {
    console.error("Error in auth callback route handler:", error)
    return NextResponse.redirect(
      new URL("/login?error=callback_internal_error", appUrl)
    )
  }
}
