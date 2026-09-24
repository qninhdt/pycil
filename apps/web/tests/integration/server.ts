import { setupServer } from "msw/node"

/**
 * The network the integration layer runs against.
 *
 * Handlers are declared per test, and an undeclared request is an error rather than a
 * pass-through — see `setup.ts`. The base URL is the same origin the browser client
 * uses in development, so the paths in a handler are the paths the app really calls.
 */
export const server = setupServer()
