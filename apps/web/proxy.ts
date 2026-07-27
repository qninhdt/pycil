import { getIronSession } from "iron-session";
import { type NextRequest, NextResponse } from "next/server";
import { sessionOptions } from "@/lib/auth/session";
import type { SessionData } from "@/lib/auth/types";

const protectedPrefixes = [
  "/dashboard",
  "/library",
  "/decks",
  "/study",
  "/search",
  "/assistant",
  "/settings",
];
const authOnlyPrefixes = ["/login"];

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const response = NextResponse.next();

  const session = await getIronSession<SessionData>(request, response, sessionOptions);
  const isLoggedIn = Boolean(session.isLoggedIn && session.accessToken);

  const isProtected = protectedPrefixes.some((prefix) => pathname.startsWith(prefix));
  const isAuthOnly = authOnlyPrefixes.some((prefix) => pathname.startsWith(prefix));

  if (isProtected && !isLoggedIn) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  if (isAuthOnly && isLoggedIn) {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|.*\\.png$).*)",
  ],
};
