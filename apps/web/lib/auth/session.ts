import { getIronSession, SessionOptions } from "iron-session";
import { cookies } from "next/headers";
import type { SessionData } from "./types";

/**
 * The cookie is the only thing standing between a visitor and someone else's
 * account, so a missing or weak password is a boot failure rather than a
 * warning. iron-session derives its AES key from this value; anything under 32
 * bytes weakens the derivation, and a committed literal would mean every
 * deployment that forgot to set the variable shares one forgeable key.
 */
function requireSessionPassword(): string {
  const password = process.env.SESSION_PASSWORD;
  if (!password) {
    throw new Error(
      "SESSION_PASSWORD is not set. Generate one with `openssl rand -base64 32`.",
    );
  }
  if (password.length < 32) {
    throw new Error(
      `SESSION_PASSWORD must be at least 32 characters, got ${password.length}. ` +
        "Generate one with `openssl rand -base64 32`.",
    );
  }
  return password;
}

/**
 * `secure` is opt-out rather than opt-in. Gating it on `NODE_ENV === production`
 * silently ships a plaintext-transmissible session cookie from any staging or
 * preview build, so the flag is on everywhere except an explicitly declared
 * local development run, where there is no TLS to attach it to.
 */
const isLocalDevelopment =
  process.env.NODE_ENV === "development" && process.env.SESSION_INSECURE_LOCAL === "true";

export const sessionOptions: SessionOptions = {
  password: requireSessionPassword(),
  cookieName: process.env.SESSION_COOKIE_NAME || "pycil_session",
  cookieOptions: {
    secure: !isLocalDevelopment,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  },
};

export const defaultSession: SessionData = {
  isLoggedIn: false,
};

/**
 * Server-only. The returned object carries `accessToken` and `refreshToken`, so
 * it must never be passed to a client component or returned from a server
 * action: either would serialise both tokens into the RSC payload as plaintext.
 * Use `toViewerSummary` in `lib/auth/viewer.ts` for anything the browser sees.
 */
export async function getSession() {
  const cookieStore = await cookies();
  const session = await getIronSession<SessionData>(cookieStore, sessionOptions);
  if (!session.isLoggedIn) {
    session.isLoggedIn = false;
  }
  return session;
}
