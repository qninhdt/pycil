import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  accessTokenForRequest: vi.fn(),
  createApiClient: vi.fn(),
  getSession: vi.fn(),
  handleAction: vi.fn(async (run: () => Promise<unknown>) => ({
    success: true as const,
    data: await run(),
  })),
  redirect: vi.fn(),
}))

vi.mock("server-only", () => ({}))
vi.mock("next/navigation", () => ({ redirect: mocks.redirect }))
vi.mock("@/lib/api/request", () => ({
  accessTokenForRequest: mocks.accessTokenForRequest,
}))
vi.mock("@/lib/api/client", () => ({
  createApiClient: mocks.createApiClient,
}))
vi.mock("@/lib/api/handle-api-error", () => ({
  handleAction: mocks.handleAction,
}))
vi.mock("@/lib/auth/session", () => ({ getSession: mocks.getSession }))

const { deleteAccount } = await import("@/lib/actions/account")

describe("account deletion session identity", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("refreshes and deletes with the same session object", async () => {
    const session = {
      accessToken: "stale-access-token",
      refreshToken: "stale-refresh-token",
      expiresAt: 10,
      refreshExpiresAt: 86_400,
      isLoggedIn: true,
      destroy: vi.fn(),
    }
    const separatelyLoadedSession = {
      ...session,
      refreshToken: "other-session-token",
    }
    const deleteAccountRequest = vi.fn(async () => undefined)
    const client = { auth: { deleteAccount: deleteAccountRequest } }

    mocks.getSession
      .mockResolvedValueOnce(session)
      .mockResolvedValueOnce(separatelyLoadedSession)
    mocks.createApiClient.mockReturnValue(client)
    mocks.accessTokenForRequest.mockImplementation(async (receivedSession) => {
      expect(receivedSession).toBe(session)
      session.refreshToken = "fresh-refresh-token"
      return "fresh-access-token"
    })
    mocks.redirect.mockImplementation(() => {
      throw new Error("redirect")
    })

    await expect(deleteAccount()).rejects.toThrow("redirect")

    expect(mocks.getSession).toHaveBeenCalledTimes(1)
    expect(mocks.createApiClient).toHaveBeenCalledWith(session, { refresh: true })
    expect(mocks.accessTokenForRequest).toHaveBeenCalledWith(session, {
      refresh: true,
    })
    expect(deleteAccountRequest).toHaveBeenCalledWith("fresh-refresh-token")
    expect(session.destroy).toHaveBeenCalledTimes(1)
  })
})
