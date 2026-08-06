import { getIronSession } from "iron-session";
import { type NextRequest, NextResponse } from "next/server";
import { sessionOptions } from "@/lib/auth/session";
import { isUsableSession } from "@/lib/auth/session-validity";
import type { SessionData } from "@/lib/auth/types";

/**
 * Route access, stated as three explicit sets rather than one prefix list.
 *
 * Prefix matching cannot express this app. `"/"` is a prefix of every path, so
 * a single `startsWith` list that protects the home route protects `/login` too,
 * and the guard then redirects `/login` to `/login` forever — the app becomes
 * unreachable for anyone who is not already signed in.
 *
 * The open set is not an oversight either. The API serves nodes and senses to an
 * anonymous caller on purpose, so a published deck can be read by someone
 * without an account. Putting those paths behind the cookie would make sharing a
 * deck pointless.
 *
 * This runs before every matched request, so it is a cheap redirect for
 * ergonomics only. It is not authorisation: each route still authorises against
 * the API server-side, which is the check that actually holds.
 */
const AUTH_ONLY = ["/login"];

const OPEN = ["/library", "/w"];

const REQUIRES_SIGN_IN = ["/", "/progress", "/settings", "/study"];

/** Exact match for `/`, prefix match with a boundary for everything else. */
function matches(pathname: string, routes: string[]): boolean {
  return routes.some((route) =>
    route === "/" ? pathname === "/" : pathname === route || pathname.startsWith(`${route}/`),
  );
}

export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const response = NextResponse.next();

  const session = await getIronSession<SessionData>(request, response, sessionOptions);
  // A present access token is not the same as a usable session: the refresh token
  // expires on its own schedule, and once it has, nothing in the cookie can be
  // revived. Gating on the token alone left the learner permanently "signed in" and
  // 401ing on every request, with nothing offering them a way to sign in again.
  const isSignedIn = isUsableSession(session);

  if (matches(pathname, AUTH_ONLY)) {
    return isSignedIn ? NextResponse.redirect(new URL("/", request.url)) : response;
  }

  if (matches(pathname, OPEN)) {
    return response;
  }

  if (matches(pathname, REQUIRES_SIGN_IN) && !isSignedIn) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("from", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: [
    "/((?!api|_next/static|_next/image|favicon.ico|sitemap.xml|robots.txt|.*\\.png$).*)",
  ],
};
