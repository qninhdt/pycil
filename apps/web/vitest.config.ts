import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  test: {
    projects: [
      { extends: true, test: { name: 'unit', environment: 'happy-dom', include: ['tests/unit/**/*.test.{ts,tsx}'] } },
      { extends: true, test: { name: 'integration', environment: 'node', include: ['tests/integration/assets/**/*.test.{ts,tsx}'] } },
    ],
  },
})
