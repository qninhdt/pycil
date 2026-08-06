/**
 * A session outlives its refresh token, and the login gate has to notice.
 *
 * The refresh token rotates on every use and expires on its own, longer schedule.
 * Once it has, nothing in the sealed cookie can be revived: every request 401s. The
 * gate used to ask only whether an access token was *present*, which stays true for
 * as long as the cookie does — so the learner was left permanently "signed in" on an
 * app that failed at everything, and nothing ever offered them a sign-in.
 *
 * The expiry was already in the cookie. It was written at the callback and rewritten
 * on every refresh, and nothing had ever read it. These tests are what make it
 * load-bearing rather than decorative.
 */

import { describe, expect, it } from "vitest"

import { isRefreshExpired, isUsableSession } from "@/lib/auth/session-validity"

const NOW = 1_800_000_000

/** A signed-in session with a live refresh token. */
function signedIn(overrides: Record<string, unknown> = {}) {
  return {
    isLoggedIn: true,
    accessToken: "an-access-token",
    refreshExpiresAt: NOW + 604_800,
    ...overrides,
  }
}

describe("isUsableSession", () => {
  it("accepts a signed-in session whose refresh token is live", () => {
    expect(isUsableSession(signedIn(), NOW)).toBe(true)
  })

  it("rejects a session whose refresh token has expired", () => {
    // The defect: `isLoggedIn` and `accessToken` are both still set — they survive in
    // the cookie — so a gate reading only those sends this learner into the app.
    const dead = signedIn({ refreshExpiresAt: NOW - 1 })
    expect(Boolean(dead.isLoggedIn && dead.accessToken)).toBe(true)
    expect(isUsableSession(dead, NOW)).toBe(false)
  })

  it("rejects a refresh token expiring exactly now", () => {
    // At the boundary the token is spent, not spendable. Treating `<=` as usable
    // would let one last refresh be attempted against a token the API has dropped.
    expect(isUsableSession(signedIn({ refreshExpiresAt: NOW }), NOW)).toBe(false)
  })

  it("accepts a cookie sealed before the field existed", () => {
    // Deploy safety, and the reason absence is not expiry: every session sealed by
    // the previous release carries no `refreshExpiresAt`, and reading that as expired
    // would sign out every existing learner the moment this ships.
    expect(isUsableSession(signedIn({ refreshExpiresAt: undefined }), NOW)).toBe(true)
  })

  it("rejects a session that was never signed in", () => {
    expect(isUsableSession(signedIn({ isLoggedIn: false }), NOW)).toBe(false)
  })

  it("rejects a session carrying no access token", () => {
    expect(isUsableSession(signedIn({ accessToken: undefined }), NOW)).toBe(false)
  })
})

describe("isRefreshExpired", () => {
  it("is false for an absent expiry", () => {
    expect(isRefreshExpired({}, NOW)).toBe(false)
  })

  it("is true only once the moment has passed", () => {
    expect(isRefreshExpired({ refreshExpiresAt: NOW + 1 }, NOW)).toBe(false)
    expect(isRefreshExpired({ refreshExpiresAt: NOW }, NOW)).toBe(true)
    expect(isRefreshExpired({ refreshExpiresAt: NOW - 1 }, NOW)).toBe(true)
  })
})
