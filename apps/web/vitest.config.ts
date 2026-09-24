import { fileURLToPath } from "node:url"

import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

/**
 * Two Vitest layers, one command each.
 *
 * `unit` is pure logic: no DOM, no network, no rendering. It runs in a node
 * environment so a test that accidentally needs a document fails loudly instead of
 * quietly working.
 *
 * `integration` renders components against controlled HTTP. The DOM comes from
 * jsdom and the network from MSW, which intercepts at the `fetch` seam — so a
 * component is exercised through its real request path rather than through a stubbed
 * action, and the response shapes are the ones the API actually sends.
 *
 * The alias is declared per project rather than at the top level: a top-level
 * `resolve.alias` is ignored inside a project block, and the failure is a confusing
 * "cannot find package '@/…'" for every import.
 */
const alias = { "@": fileURLToPath(new URL("./", import.meta.url)) }

export default defineConfig({
  test: {
    projects: [
      {
        plugins: [react()],
        resolve: { alias },
        test: {
          name: "unit",
          environment: "node",
          include: ["tests/unit/**/*.test.ts"],
        },
      },
      {
        plugins: [react()],
        resolve: { alias },
        test: {
          name: "integration",
          environment: "jsdom",
          include: ["tests/integration/**/*.test.tsx"],
          setupFiles: ["tests/integration/setup.ts"],
        },
      },
    ],
  },
})
