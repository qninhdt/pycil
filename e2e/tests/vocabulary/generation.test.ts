import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { test, expect } from '../../fixtures/index.ts'
import { directory } from '../../support/environment.ts'
import { structuredCompletion } from '../../support/model-provider.ts'

test('failed generation can retry, pending work remains visible and publication updates real search', async ({ user, scenarios }) => {
  const id = randomUUID()
  const payload = JSON.parse(await readFile(`${directory}/support/data/provider-scenarios.json`, 'utf8')) as { quay: { inventory: unknown; enrichment: unknown } }
  await scenarios.register({ id, path: '/chat/completions', contains: 'quay', responses: [
    { status: 400, body: { error: { type: 'invalid_request_error', message: 'Controlled generation failure' } } },
    { status: 200, body: structuredCompletion(payload.quay.inventory), hold: true },
    { status: 200, body: structuredCompletion(payload.quay.enrichment) },
  ] })
  await user.page.goto('/app/dictionary?q=quay')
  await user.page.getByRole('button').filter({ hasText: 'quay' }).click()
  await user.page.getByRole('button', { name: 'Prepare entry', exact: true }).click()
  await expect(user.page.getByRole('alert').filter({ hasText: /Preparation failed/ })).toBeVisible()
  await user.page.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(user.page.getByRole('status').filter({ hasText: /Generating/ })).toBeVisible()
  expect(await user.api.call('study/progress')).toMatchObject({ total: 0 })
  await scenarios.release(id)
  await expect(user.page.getByRole('heading', { name: 'quay', exact: true })).toBeVisible()
  await expect(user.page.locator('article')).toContainText('a structure beside water where boats stop to load and unload')
  const search = await user.api.call<{ items: { kind: string; word_id?: number }[] }>('words:search?query=quay&include_reference=true')
  expect(search.items[0].kind).toBe('word')
  const wordId = search.items[0].word_id!
  const word = await user.api.call<{ senses: { examples: unknown[] }[] }>(`words/${wordId}`)
  expect(word.senses[0].examples).toHaveLength(5)
  await user.page.reload()
  await expect(user.page.getByRole('heading', { name: 'quay', exact: true })).toBeVisible()
  expect(await user.api.call('study/progress')).toMatchObject({ total: 0 })
})
