import { randomUUID } from 'node:crypto'
import { test, expect, api } from './fixtures'
import { start, finish, session } from './study-session'
import type { WordGeneration } from '../src/lib/dictionary-model'

test('guest search/detail uses native markup, has honest misses and keeps private context unavailable', async ({ page }) => {
  await page.goto('/app/dictionary?q=bank')
  await page.getByRole('button', { name: 'bank Ready', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'bank', exact: true })).toBeVisible()
  await expect(page.getByText('I visited the bank.', { exact: true }).first()).toBeVisible()
  expect(await page.locator('t').count()).toBe(0)
  expect((await api(page, 'words/1', 'GET', undefined, false)).status).toBe(200)
  expect((await api(page, 'me/words/1', 'GET', undefined, false)).status).toBe(401)
  await page.getByRole('searchbox', { name: 'Search word or expression' }).fill('zzznoentry')
  await expect(page.getByText('No entries found. Try another spelling or expression.')).toBeVisible()
  await page.getByRole('button', { name: 'Clear search' }).click()
  await expect(page.getByText('Search for a word or expression to explore its meanings.')).toBeVisible()
})

test('a delayed older native Dictionary query cannot replace the latest search', async ({ page }) => {
  let release!: () => void, reached!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const requested = new Promise<void>(resolve => { reached = resolve })
  await page.route('**/api/v1/words:search*', async route => {
    if (new URL(route.request().url()).searchParams.get('query') === 'bank') { reached(); await gate }
    await route.continue()
  })
  await page.goto('/app/dictionary')
  const search = page.getByRole('searchbox', { name: 'Search word or expression' })
  await search.fill('bank'); await requested
  await search.fill('archive')
  await expect(page.getByRole('button', { name: 'archive Ready', exact: true })).toBeVisible()
  release()
  await expect(page.getByRole('button', { name: 'bank Ready', exact: true })).not.toBeVisible()
  await page.getByRole('button', { name: 'archive Ready', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'archive', exact: true })).toBeVisible()
})

test('picker keeps selected meanings across searches, sends batched native reads and preserves concurrent membership', async ({ page, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [32] })
  await page.goto(`/app/personal/${deck.id}/words`)
  await page.getByRole('button', { name: 'Add words', exact: true }).click()
  const picker = page.getByRole('dialog', { name: 'Add words to deck' })
  const batch = page.waitForResponse(response => response.url().endsWith('/words:batchPreview'))
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('bank')
  expect((await batch).status()).toBe(200)
  await picker.getByRole('checkbox').first().check()
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('archive')
  await expect(picker.getByRole('checkbox').first()).toBeVisible()
  await picker.getByRole('checkbox').first().check()
  await expect(picker.getByText('2 meanings selected', { exact: true })).toBeVisible()
  expect((await api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [31], remove: [] })).status).toBe(200)
  await picker.getByRole('button', { name: 'Add to deck', exact: true }).click()
  await expect(picker).not.toBeVisible()
  const membership = (await api<{ senses: { sense_id: number }[] }>(page, `nodes/${deck.id}/senses?limit=100`)).body
  expect(membership.senses.map(sense => sense.sense_id).sort((a, b) => a - b)).toEqual([1, 31, 32, 100])
  await page.reload()
  await expect(page.getByRole('button', { name: /^View / })).toHaveCount(4)
})

test('Dictionary creates a real deck in a nested destination with the selected sense', async ({ page, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const name = 'dictionary-' + randomUUID()
  await page.goto('/app/dictionary?q=bank')
  await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText('Free plan')
  await page.getByRole('button', { name: 'bank Ready', exact: true }).click()
  await page.getByRole('button', { name: 'Add to deck', exact: true }).first().click()
  const destination = page.getByRole('dialog', { name: 'Choose a destination' })
  await destination.getByRole('button', { name: 'Personal', exact: true }).dblclick()
  await destination.getByRole('button', { name: folder.name, exact: true }).dblclick()
  await destination.getByRole('button', { name: `Create a deck in ${folder.name}`, exact: true }).click()
  await destination.getByRole('textbox', { name: 'New deck name' }).fill(name)
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/nodes') && r.request().method() === 'POST')
  await destination.getByRole('button', { name: 'Create and add', exact: true }).click()
  const response = await created
  expect(response.status()).toBe(201)
  const deck = await response.json(); nodes.track(deck.id)
  expect(deck.parent_id).toBe(folder.id)
  expect(deck.sense_ids).toEqual([1])
  await page.goto(`/app/personal/${deck.id}/words`)
  await expect(page.getByRole('button', { name: /^View bank:/ })).toHaveCount(1)
})

for (const target of ['harbor', 'quay', 'glistening', 'glisten with something']) test(`native ${target} generation${target === 'quay' ? ' exposes provider failure and retries' : ' publishes readable senses'}`, async ({ page, profile }) => {
  expect(profile.id).toBeTruthy()
  await page.goto('/app/dictionary?q=' + target)
  await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText('Free plan')
  await page.getByRole('button', { name: target + ' Needs preparation Generate', exact: true }).click()
  const queued = page.waitForResponse(r => r.url().endsWith('/words:generate') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Prepare entry', exact: true }).click()
  const response = await queued
  expect(response.status()).toBe(202)
  let job: WordGeneration = await response.json()
  expect(['RUNNING']).toContain(job.status)
  if (target === 'quay') {
    await expect(page.getByRole('alert').filter({ hasText: 'Preparation failed' })).toBeVisible()
    const retry = page.waitForResponse(r => r.url().endsWith('/words:generate') && r.request().method() === 'POST')
    await page.getByRole('alert').filter({ hasText: 'Preparation failed' }).getByRole('button', { name: 'Retry', exact: true }).click()
    const retried = await retry
    expect(retried.status()).toBe(202)
    const next: WordGeneration = await retried.json()
    expect(next.task_id).not.toBe(job.task_id)
    expect((await api<WordGeneration>(page, `word-tasks/${job.task_id}`)).body.status).toBe('FAILED')
    job = next
  }
  const lemma = target === 'glistening' ? 'glisten' : target === 'glisten with something' ? 'glisten with {sth}' : target
  await expect(page.getByRole('heading', { name: lemma, exact: true })).toBeVisible()
  await expect.poll(async () => (await api<WordGeneration>(page, `word-tasks/${job.task_id}`)).body.status).toBe('SUCCEEDED')
  const stored = (await api<WordGeneration>(page, `word-tasks/${job.task_id}`)).body
  expect(stored.word_id).toBeGreaterThan(2)
  const word = await api<{ senses: { id: number }[] }>(page, `words/${stored.word_id}`)
  expect(word.status).toBe(200); expect(word.body.senses.length).toBeGreaterThan(0)
  expect(word.body.senses.every(sense => !('usage_note' in sense))).toBe(true)
  expect((await api(page, 'words:generate', 'POST', { reference_id: 'invalid', target })).status).toBe(422)
})


test('generation retains valid examples and learning generates native artifacts on demand', async ({ page, profile, nodes }) => {
  await page.goto('/app/dictionary?q=jetty')
  await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText('Free plan')
  await page.getByRole('button', { name: 'jetty Needs preparation Generate', exact: true }).click()
  const created = page.waitForResponse(r => r.url().endsWith('/words:generate') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Prepare entry', exact: true }).click()
  const job: WordGeneration = await (await created).json()
  await expect(page.getByRole('heading', { name: 'jetty', exact: true })).toBeVisible()
  const saved = (await api<WordGeneration>(page, `word-tasks/${job.task_id}`)).body
  expect(saved.status).toBe('SUCCEEDED'); expect(saved.stage).toBe('READY')
  const word = (await api<{ senses: { id: number; examples: { content: string }[] }[] }>(page, `words/${saved.word_id}`)).body
  expect(word.senses[0].examples.map(example => example.content)).toEqual(['Ships dock at the [jetty].'])
  await expect(page.getByText('Ships dock at the jetty.', { exact: true })).toBeVisible()
  expect(await page.locator('t').count()).toBe(0)
  const deck = await nodes.create({ type: 'DECK', sense_ids: [word.senses[0].id] })
  const prepared = page.waitForResponse(r => r.url().endsWith('/study:prepare'))
  await start(page, deck.id)
  expect((await (await prepared).json()).actual_question_count).toBe(3)
  await finish(page, profile.id)
  await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
  expect((await session(page, profile.id))!.receipt!.results).toHaveLength(1)
})
