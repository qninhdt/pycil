/**
 * A refreshed token has to outlive the request that refreshed it.
 *
 * `ensureAccessToken` swaps in a new access/refresh pair when the old one is
 * close to expiry, writing the new values onto the session object. That object
 * is a sealed cookie: mutating it in memory changes nothing the browser will
 * send back. Unless something calls `save()`, the next request arrives with the
 * *old* refresh token, which the API has already rotated away — so the session
 * looks signed in while every call it makes returns 401.
 *
 * The complication is that a cookie cannot be written during render. Next.js
 * throws when a server component tries. So persistence has to be attempted and
 * allowed to fail quietly: a mutating action or route handler seals the cookie,
 * a render-time read uses the fresh token for that request only. These tests pin
 * both halves — that save is attempted, and that a render-context failure does
 * not take the request down with it.
 */

import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("server-only", () => ({}))

const { createFetcher } = await import("@/lib/api/request")

type MutableSession = {
  accessToken?: string
  refreshToken?: string
  expiresAt?: number
  refreshExpiresAt?: number
  isLoggedIn: boolean
  save?: () => Promise<void>
}

/** A session whose access token expires inside the refresh window. */
function expiringSession(overrides: Partial<MutableSession> = {}): MutableSession {
  const now = Math.floor(Date.now() / 1000)
  return {
    accessToken: "stale-access-token",
    refreshToken: "stale-refresh-token",
    // 10s of life left, well inside the 60s refresh window.
    expiresAt: now + 10,
    refreshExpiresAt: now + 86_400,
    isLoggedIn: true,
    ...overrides,
  }
}

function mockFetchSequence() {
  const refreshResponse = {
    ok: true,
    status: 200,
    json: async () => ({
      accessToken: "fresh-access-token",
      refreshToken: "fresh-refresh-token",
      expiresIn: 3600,
      refreshExpiresIn: 604_800,
    }),
  }
  const apiResponse = {
    ok: true,
    status: 200,
    headers: new Headers({ "content-type": "application/json" }),
    json: async () => ({ ok: true }),
    text: async () => '{"ok":true}',
  }
  return vi
    .fn()
    .mockResolvedValueOnce(refreshResponse as unknown as Response)
    .mockResolvedValueOnce(apiResponse as unknown as Response)
}

describe("token refresh persistence", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it("persists the refreshed pair so the next request does not reuse a rotated token", async () => {
    const save = vi.fn(async () => {})
    const session = expiringSession({ save })
    vi.stubGlobal("fetch", mockFetchSequence())

    await createFetcher(session as never)("/v1/anything")

    // The in-memory swap is necessary but not sufficient.
    expect(session.accessToken).toBe("fresh-access-token")
    expect(session.refreshToken).toBe("fresh-refresh-token")

    // This is the defect: without a save, the sealed cookie still holds
    // `stale-refresh-token`, which the API has already invalidated by rotation.
    expect(save).toHaveBeenCalledTimes(1)
  })

  it("still serves the request when the cookie cannot be written during render", async () => {
    // Next.js throws exactly this way when a server component tries to set a
    // cookie. A read-time refresh must degrade to "fresh token for this request
    // only" rather than turning a page render into an error.
    const save = vi.fn(async () => {
      throw new Error("Cookies can only be modified in a Server Action or Route Handler")
    })
    const session = expiringSession({ save })
    vi.stubGlobal("fetch", mockFetchSequence())

    await expect(createFetcher(session as never)("/v1/anything")).resolves.toEqual({
      ok: true,
    })

    expect(save).toHaveBeenCalledTimes(1)
    expect(session.accessToken).toBe("fresh-access-token")
  })

  it("does not attempt a save when no refresh happened", async () => {
    const save = vi.fn(async () => {})
    const now = Math.floor(Date.now() / 1000)
    // Comfortably outside the refresh window: nothing to persist.
    const session = expiringSession({ save, expiresAt: now + 3600 })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ ok: true }),
      text: async () => '{"ok":true}',
    } as unknown as Response)
    vi.stubGlobal("fetch", fetchMock)

    await createFetcher(session as never)("/v1/anything")

    expect(save).not.toHaveBeenCalled()
    // One call for the API request; none for a refresh.
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it("does not attempt a save when the refresh call fails", async () => {
    const save = vi.fn(async () => {})
    const session = expiringSession({ save })
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({ ok: false, status: 401 } as unknown as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ ok: true }),
          text: async () => '{"ok":true}',
        } as unknown as Response),
    )

    await createFetcher(session as never)("/v1/anything")

    // Nothing changed, so sealing the cookie again would be pure overhead.
    expect(save).not.toHaveBeenCalled()
    expect(session.refreshToken).toBe("stale-refresh-token")
  })

  it("does not spend a round trip on a refresh token that has expired", async () => {
    const save = vi.fn(async () => {})
    const now = Math.floor(Date.now() / 1000)
    // Inside the refresh window, so a refresh would ordinarily be attempted — but
    // the refresh token itself is already gone, and the API can only say so.
    const session = expiringSession({ save, refreshExpiresAt: now - 1 })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ ok: true }),
      text: async () => '{"ok":true}',
    } as unknown as Response)
    vi.stubGlobal("fetch", fetchMock)

    await createFetcher(session as never)("/v1/anything")

    // One call for the API request; none for a refresh that could not succeed. The
    // login gate reads the same field, so this learner is already on their way to
    // `/login` rather than waiting on a round trip to be told no.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(save).not.toHaveBeenCalled()
  })
})
