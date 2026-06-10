import type { NextAuthConfig } from "next-auth";

const cookieName =
  process.env.NODE_ENV === "production"
    ? "__Secure-pycil-session"
    : "pycil-session";

export const authConfig = {
  pages: { signIn: "/sign-in" },
  trustHost: true,
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const isOnSignIn = nextUrl.pathname.startsWith("/sign-in");
      if (isOnSignIn) return true;
      if (!isLoggedIn) {
        const url = new URL("/sign-in", nextUrl);
        url.searchParams.set("callbackUrl", nextUrl.pathname);
        return Response.redirect(url);
      }
      // Edge gate for /admin/* — convenience only; the backend DB role read is
      // authoritative. Non-admins are bounced to the dashboard.
      if (nextUrl.pathname.startsWith("/admin")) {
        const role = (auth?.user as { role?: string } | undefined)?.role;
        if (role !== "admin") {
          return Response.redirect(new URL("/", nextUrl));
        }
      }
      return true;
    },
  },
  cookies: {
    sessionToken: {
      name: cookieName,
      options: {
        httpOnly: true,
        sameSite: "lax",
        path: "/",
        secure: process.env.NODE_ENV === "production",
      },
    },
  },
  providers: [],
} satisfies NextAuthConfig;
