import { request, expect } from '@playwright/test'
import type { Scenario } from '../support/model-provider.ts'
import { providerURL } from '../support/environment.ts'

export async function createScenarios() {
  if (process.env.E2E_PROVIDER_PROFILE === 'live') throw new Error('Controlled scenarios are forbidden in live E2E')
  const client = await request.newContext({ baseURL: providerURL })
  const ids: string[] = []
  return {
    async register(scenario: Scenario) {
      const response = await client.post('/scenarios', { data: scenario })
      if (response.status() !== 201) throw new Error(`Scenario registration failed: HTTP ${response.status()}`)
      ids.push(scenario.id)
    },
    async release(id: string) {
      if (!ids.includes(id)) throw new Error('Cannot release another test’s scenario')
      const response = await client.post(`/scenarios/${id}/release`)
      if (!response.ok()) throw new Error('Scenario release failed')
    },
    async settled(id: string) {
      if (!ids.includes(id)) throw new Error('Cannot inspect another test’s scenario')
      await expect.poll(async () => {
        const response = await client.get(`/scenarios/${id}`)
        if (!response.ok()) throw new Error('Scenario diagnostics unavailable')
        return (await response.json() as { active: number }).active
      }).toBe(0)
    },
    async cleanup() {
      const errors: Error[] = []
      try {
        for (const id of ids) {
          try {
            await client.post(`/scenarios/${id}/release`)
            await expect.poll(async () => (await (await client.get(`/scenarios/${id}`)).json() as { active: number }).active).toBe(0)
            const response = await client.get(`/scenarios/${id}`)
            if (!response.ok()) throw new Error(`Scenario ${id} diagnostics unavailable`)
            const stats = await response.json() as { consumed: number; expected: number }
            if (stats.consumed !== stats.expected) errors.push(new Error(`Scenario ${id}: consumed ${stats.consumed}/${stats.expected} calls`))
          } catch { errors.push(new Error(`Scenario ${id} verification failed`)) }
          try {
            const response = await client.delete(`/scenarios/${id}`)
            if (response.status() !== 200) throw new Error('Unexpected deletion status')
          } catch { errors.push(new Error(`Scenario ${id} cleanup failed`)) }
        }
      } finally { await client.dispose() }
      if (errors.length) throw new AggregateError(errors, 'Controlled scenario verification/cleanup failed')
    },
  }
}
