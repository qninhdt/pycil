import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  createApiClient: vi.fn(),
  getSession: vi.fn(),
}))

vi.mock("server-only", () => ({}))
vi.mock("@/lib/api/client", () => ({
  createApiClient: mocks.createApiClient,
}))
vi.mock("@/lib/auth/session", () => ({ getSession: mocks.getSession }))

const { SessionPersistenceError } = await import("@/lib/api/request")
const { getRealtimeToken } = await import("@/lib/actions/realtime")

describe("realtime token persistence", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("does not turn a cookie-write failure into an anonymous result", async () => {
    const session = { isLoggedIn: true }
    const persistenceError = new SessionPersistenceError()
    const getToken = vi.fn(async () => {
      throw persistenceError
    })
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {})

    mocks.getSession.mockResolvedValue(session)
    mocks.createApiClient.mockReturnValue({ auth: { getRealtimeToken: getToken } })

    await expect(getRealtimeToken()).rejects.toBe(persistenceError)
    expect(errorSpy).toHaveBeenCalledWith(
      "Failed to persist session while fetching realtime token:",
      persistenceError,
    )

    errorSpy.mockRestore()
  })
})
