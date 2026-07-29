import { type NextRequest, NextResponse } from "next/server";
import {
  isSafeReturnPath,
  RETURN_PATH_COOKIE,
  RETURN_PATH_MAX_AGE,
} from "@/lib/auth/return-path";

import type { LoginStart } from "@/lib/api/types";

export async function GET(request: NextRequest) {
  const apiUrl = process.env.PYCIL_API_URL || "http://localhost:8000";
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  const redirectUri = `${appUrl}/api/auth/callback`;
  const returnPath = request.nextUrl.searchParams.get("from");

  try {
    const res = await fetch(`${apiUrl}/v1/auth/login?redirect_uri=${encodeURIComponent(redirectUri)}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      const errorText = await res.text();
      console.error("Failed to fetch login authorize_url from Pycil API:", res.status, errorText);
      return NextResponse.redirect(new URL("/login?error=auth_init_failed", appUrl));
    }

    const data: LoginStart = await res.json();
    const response = NextResponse.redirect(data.authorizeUrl);

    // Where the guard sent them from, held for the round trip so a deep link to
    // /progress does not silently land on / after sign-in. Validated here rather
    // than on return: an unsafe value is never worth storing.
    if (isSafeReturnPath(returnPath)) {
      response.cookies.set(RETURN_PATH_COOKIE, returnPath, {
        httpOnly: true,
        sameSite: "lax",
        secure: new URL(appUrl).protocol === "https:",
        path: "/api/auth/callback",
        maxAge: RETURN_PATH_MAX_AGE,
      });
    }

    return response;
  } catch (error) {
    console.error("Error in login route handler:", error);
    return NextResponse.redirect(new URL("/login?error=network_error", appUrl));
  }
}
