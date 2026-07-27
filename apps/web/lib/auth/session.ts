import { getIronSession, SessionOptions } from "iron-session";
import { cookies } from "next/headers";
import type { SessionData } from "./types";

export const sessionOptions: SessionOptions = {
  password: process.env.SESSION_PASSWORD || "complex-password-at-least-32-chars-long-for-iron-session",
  cookieName: process.env.SESSION_COOKIE_NAME || "pycil_session",
  cookieOptions: {
    secure: process.env.NODE_ENV === "production",
    httpOnly: true,
    sameSite: "lax",
    path: "/",
  },
};

export const defaultSession: SessionData = {
  isLoggedIn: false,
};

export async function getSession() {
  const cookieStore = await cookies();
  const session = await getIronSession<SessionData>(cookieStore, sessionOptions);
  if (!session.isLoggedIn) {
    session.isLoggedIn = false;
  }
  return session;
}
