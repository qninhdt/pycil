import type { NextAuthConfig } from "next-auth";

/**
 * Edge-safe Auth.js v5 config.
 *
 * Defines providers + authorize callback for middleware. The Postgres adapter
 * lives in `auth.ts` (Node-only, not edge-safe).
 */
export const authConfig = {
  pages: { signIn: "/" },
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const onProtected = nextUrl.pathname.startsWith("/dashboard");
      if (onProtected && !isLoggedIn) {
        return Response.redirect(new URL("/", nextUrl));
      }
      return true;
    },
  },
  cookies: {
    sessionToken: {
      // Auth.js v5 default name. We force SameSite=Strict (PDR §5 CSRF defense).
      name:
        process.env.NODE_ENV === "production"
          ? "__Secure-authjs.session-token"
          : "authjs.session-token",
      options: {
        httpOnly: true,
        sameSite: "strict",
        path: "/",
        secure: process.env.NODE_ENV === "production",
      },
    },
  },
  providers: [],
} satisfies NextAuthConfig;
