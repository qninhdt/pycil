import type { SessionData } from "./types";

/**
 * Whether a sealed session can still act on the learner's behalf.
 *
 * The login gate used to ask only whether an access token was present. That is
 * true for as long as the cookie survives — a week past the point the API stopped
 * honouring anything in it. The refresh token rotates on every use and expires on
 * its own schedule; once it has, no request can be revived, and the session becomes
 * a cookie that says "signed in" while every call it makes returns 401. The learner
 * sees an app that loads its shell and then fails at everything, with no sign-in
 * prompt, because the only thing that would have offered one was satisfied by the
 * presence of a token rather than by its usability.
 *
 * So the expiry the cookie already carried is finally read. It was written at the
 * callback and rewritten on every refresh, and nothing had ever looked at it.
 */

/**
 * True when the session's refresh token is beyond saving.
 *
 * `undefined` is deliberately *not* expired. Cookies sealed before this field was
 * written carry no value for it, and treating their absence as expiry would sign
 * out every existing learner on deploy — turning a fix for a stale-session bug into
 * a much louder one. They are re-sealed with the field on their next refresh.
 */
export function isRefreshExpired(
  session: Pick<SessionData, "refreshExpiresAt">,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): boolean {
  return session.refreshExpiresAt !== undefined && session.refreshExpiresAt <= nowSeconds;
}

/**
 * Whether the login gate should treat this session as signed in.
 *
 * Not authorisation — every route still authorises against the API server-side,
 * which is the check that actually holds. This decides only whether to send someone
 * to `/login`, and the point is that it now sends them there while a sign-in can
 * still fix something, rather than leaving them on a page that 401s.
 */
export function isUsableSession(
  session: Pick<SessionData, "isLoggedIn" | "accessToken" | "refreshExpiresAt">,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): boolean {
  return Boolean(
    session.isLoggedIn && session.accessToken && !isRefreshExpired(session, nowSeconds),
  );
}
