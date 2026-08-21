import { NextResponse } from "next/server"
import { apiUrl } from "@/lib/api/upstream"
import { getSession } from "@/lib/auth/session"

export async function POST() {
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000"

  try {
    const session = await getSession()

    if (session.refreshToken) {
      // Call Pycil API to revoke refresh token
      await fetch(`${apiUrl()}/v1/auth/logout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(session.accessToken
            ? { Authorization: `Bearer ${session.accessToken}` }
            : {}),
        },
        body: JSON.stringify({ refresh_token: session.refreshToken }),
        cache: "no-store",
      }).catch((err) => {
        console.warn("Failed to notify Pycil API on logout:", err)
      })
    }

    // Destroy local session cookie
    session.destroy()

    return NextResponse.redirect(new URL("/login", appUrl), { status: 303 })
  } catch (error) {
    console.error("Error in logout route handler:", error)
    return NextResponse.redirect(new URL("/login", appUrl), { status: 303 })
  }
}
