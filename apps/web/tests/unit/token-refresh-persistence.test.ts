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
 * throws when a server component tries. Plain Server Component reads therefore
 * opt out of refresh; mutation-capable actions and route handlers opt in and must
 * fail rather than return a fresh token backed by a stale cookie.
 */

import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("server-only", () => ({}))

const { createFetcher, SessionPersistenceError } = await import("@/lib/api/request")
const { createApiClient } = await import("@/lib/api/client")

type MutableSession = {
  accessToken?: string
  refreshToken?: string
  expiresAt?: number
  refreshExpiresAt?: number
  isLoggedIn: boolean
  save?: () => Promise<void>
}

/** A session whose access token expires inside the refresh window. */
function expiringSession(
  overrides: Partial<MutableSession> = {}
): MutableSession {
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

  it("fails when an opted-in refresh cannot write the cookie", async () => {
    // Next.js throws exactly this way when a server component tries to set a
    // cookie. An opted-in refresh must fail rather than return a fresh token backed
    // by a stale cookie.
    const save = vi.fn(async () => {
      throw new Error(
        "Cookies can only be modified in a Server Action or Route Handler"
      )
    })
    const session = expiringSession({ save })
    vi.stubGlobal("fetch", mockFetchSequence())

    const request = createFetcher(session as never)("/v1/anything")
    await expect(request).rejects.toBeInstanceOf(SessionPersistenceError)
    await expect(request).rejects.toThrow(
      "Could not persist the refreshed session after token rotation",
    )

    expect(save).toHaveBeenCalledTimes(1)
    expect(session.accessToken).toBe("fresh-access-token")
  })

  it("does not rotate a token for a non-persisting Server Component read", async () => {
    const save = vi.fn(async () => {})
    const session = expiringSession({ save })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ ok: true }),
      text: async () => '{"ok":true}',
    } as unknown as Response)
    vi.stubGlobal("fetch", fetchMock)

    await expect(
      createFetcher(session as never, { refresh: false })("/v1/anything"),
    ).resolves.toEqual({ ok: true })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(session.refreshToken).toBe("stale-refresh-token")
    expect(save).not.toHaveBeenCalled()
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

  it("defaults the typed API client to non-refreshing reads", async () => {
    const save = vi.fn(async () => {})
    const session = expiringSession({ save })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ ok: true }),
      text: async () => '{"ok":true}',
    } as unknown as Response)
    vi.stubGlobal("fetch", fetchMock)

    await expect(createApiClient(session as never).auth.getViewer()).resolves.toEqual({
      ok: true,
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/v1\/me$/)
    expect(session.refreshToken).toBe("stale-refresh-token")
    expect(save).not.toHaveBeenCalled()
  })

  it("shares one refresh when concurrent reads use the same session", async () => {
    const save = vi.fn(async () => {})
    const session = expiringSession({ save })
    let releaseRefresh!: () => void
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve
    })
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
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/v1/auth/refresh")) {
        await refreshGate
        return refreshResponse as unknown as Response
      }
      return apiResponse as unknown as Response
    })
    vi.stubGlobal("fetch", fetchMock)

    const first = createFetcher(session as never)("/v1/first")
    const second = createFetcher(session as never)("/v1/second")
    await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    releaseRefresh()
    await expect(Promise.all([first, second])).resolves.toEqual([
      { ok: true },
      { ok: true },
    ])
    expect(
      fetchMock.mock.calls.filter(([url]) => url.endsWith("/v1/auth/refresh"))
    ).toHaveLength(1)
    expect(save).toHaveBeenCalledTimes(1)
  })

  it("shares one refresh across separately deserialized sessions", async () => {
    const firstSave = vi.fn(async () => {})
    const secondSave = vi.fn(async () => {})
    const firstSession = expiringSession({ save: firstSave })
    const secondSession = expiringSession({ save: secondSave })
    let releaseRefresh!: () => void
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve
    })
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
    const fetchMock = vi.fn(async (url: string) => {
      if (url.endsWith("/v1/auth/refresh")) {
        await refreshGate
        return refreshResponse as unknown as Response
      }
      return apiResponse as unknown as Response
    })
    vi.stubGlobal("fetch", fetchMock)

    const first = createFetcher(firstSession as never)("/v1/first")
    const second = createFetcher(secondSession as never)("/v1/second")
    await Promise.resolve()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    releaseRefresh()
    await expect(Promise.all([first, second])).resolves.toEqual([
      { ok: true },
      { ok: true },
    ])
    expect(
      fetchMock.mock.calls.filter(([url]) => url.endsWith("/v1/auth/refresh")),
    ).toHaveLength(1)
    expect(firstSave).toHaveBeenCalledTimes(1)
    expect(secondSave).toHaveBeenCalledTimes(1)
  })

  it("does not attempt a save when the refresh call fails", async () => {
    const save = vi.fn(async () => {})
    const session = expiringSession({ save })
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: false,
          status: 401,
        } as unknown as Response)
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({ ok: true }),
          text: async () => '{"ok":true}',
        } as unknown as Response)
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
