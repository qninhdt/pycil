import { NextResponse } from "next/server";

export async function GET() {
  const apiUrl = process.env.PYCIL_API_URL || "http://localhost:8000";
  const appUrl = process.env.NEXT_PUBLIC_APP_URL || "http://localhost:3000";
  const redirectUri = `${appUrl}/api/auth/callback`;

  try {
    const res = await fetch(`${apiUrl}/v1/auth/login?redirect_uri=${encodeURIComponent(redirectUri)}`, {
      cache: "no-store",
    });

    if (!res.ok) {
      const errorText = await res.text();
      console.error("Failed to fetch login authorize_url from Pycil API:", res.status, errorText);
      return NextResponse.redirect(new URL("/login?error=auth_init_failed", appUrl));
    }

    const data = (await res.json()) as { authorize_url: string };
    return NextResponse.redirect(data.authorize_url);
  } catch (error) {
    console.error("Error in login route handler:", error);
    return NextResponse.redirect(new URL("/login?error=network_error", appUrl));
  }
}
