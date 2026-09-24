import { cleanup } from "@testing-library/react"
import { afterEach, vi } from "vitest"

import { server } from "./server"

/**
 * The integration layer's shared setup: a DOM, a controlled network, and no Next.js.
 *
 * `server.listen({ onUnhandledRequest: "error" })` is the important line. A component
 * that reaches for an endpoint no test declared is a component whose request the test
 * author did not think about — usually a new call added to the code under test. Letting
 * that through as a real request would make the suite depend on whatever happens to be
 * listening, and letting it fail silently would hide it. Failing loudly names the URL.
 */
server.listen({ onUnhandledRequest: "error" })

// jsdom ships neither of these, and both are used by the app's real code paths:
// `next/navigation` calls `scrollTo` on a route change, and the export card builds an
// object URL for the download it triggers.
Object.defineProperty(window, "scrollTo", { value: vi.fn(), writable: true })
URL.createObjectURL = vi.fn(() => "blob:test")
URL.revokeObjectURL = vi.fn()

afterEach(() => {
  cleanup()
  server.resetHandlers()
})
