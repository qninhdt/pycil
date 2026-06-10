import { NextResponse } from "next/server";
import { auth } from "./auth";

// In mock mode the app runs without a backend and without real auth, so bypass
// the Auth.js gate entirely — the seeded demo user reaches every route.
// NEXT_PUBLIC_* is inlined at build time, so this is readable in the edge runtime.
const bypass = () => NextResponse.next();

export const middleware =
  process.env.NEXT_PUBLIC_USE_MOCK === "true" ? bypass : auth;

export const config = {
  matcher: [
    // Public routes excluded from auth: NextAuth endpoints, Next internals,
    // the sign-in page, and the legal pages (privacy/terms must be reachable
    // when signed out — OAuth consent links to them).
    "/((?!api/auth|_next/static|_next/image|favicon.ico|sign-in|legal).*)",
  ],
};
