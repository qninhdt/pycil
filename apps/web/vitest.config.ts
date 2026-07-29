import { fileURLToPath } from "node:url"

import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

/**
 * Unit-layer config: pure logic only, no DOM and no network.
 *
 * The three layers are kept distinct on purpose. Component behaviour is asserted in
 * Storybook and Playwright, where it is truer and cheaper; this layer is for the
 * functions that take values and return values — the transcript fold, the SSE frame
 * parser, and anything else whose bugs are logic bugs rather than render bugs.
 *
 * The `@/` alias mirrors `tsconfig.json` so a test imports a module by the same path
 * the app does, rather than a relative path that would drift when the module moves.
 */
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "node",
    include: ["tests/unit/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
})
