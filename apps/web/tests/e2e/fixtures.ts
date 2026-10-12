import { test as base,expect } from '@playwright/test'
import { randomUUID } from 'node:crypto'
import type { AccountProfile } from '../../src/lib/api'
import { api } from './helpers/api'
import { signIn } from './helpers/auth'
import { trackBrowserErrors } from './helpers/browser-errors'

type Node = { id: string; name: string; sense_ids?: number[]; parent_id: string; space: string }
type Fixtures = {
  browserErrors: void
  profile: AccountProfile
  nodes: { create: (input: { type: 'FOLDER' | 'DECK'; name?: string; parent_id?: string; sense_ids?: number[] }) => Promise<Node>; track: (id: string) => void }
}

export const test = base.extend<Fixtures>({
  browserErrors: [async ({ browser, context }, provide, testInfo) => {
    const guard = trackBrowserErrors(browser, context)
    try { await provide() } finally {
      guard.dispose()
      if (testInfo.status !== testInfo.expectedStatus && guard.consoleErrors.length) await testInfo.attach('browser-console', { body: guard.consoleErrors.join('\n\n'), contentType: 'text/plain' })
      expect(guard.errors, 'Unexpected browser exceptions in any test-owned context').toEqual([])
    }
  }, { auto: true }],
  profile: async ({ page }, provide) => { await provide(await signIn(page)) },
  nodes: async ({ page, profile }, provide) => {
    const owned = new Set<string>()
    try { await provide({
      track: id => { owned.add(id) },
      create: async input => {
        const response = await api<Node>(page, 'nodes', 'POST', { ...input, name: input.name ?? `e2e-${randomUUID()}`, parent_id: input.parent_id ?? profile.personal_node_id, ...(input.type === 'DECK' ? { sense_ids: input.sense_ids ?? [] } : {}) })
        expect(response.status).toBe(201)
        owned.add(response.body.id)
        return response.body
      },
    }) } finally {
      const failures: string[] = []
      for (const id of [...owned].reverse()) {
        try {
          const result = await api(page, `nodes/${encodeURIComponent(id)}`, 'DELETE')
          if (![204, 404].includes(result.status)) failures.push(`${id}: HTTP ${result.status}`)
        } catch { failures.push(`${id}: cleanup request failed`) }
      }
      expect(failures, 'Cleanup of test-owned nodes').toEqual([])
    }
  },
})

export { expect }
export const proTest = test.extend<Fixtures>({ profile: async ({ page }, provide) => { await provide(await signIn(page, 'B')) } })
