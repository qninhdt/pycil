import { expect,test } from './fixtures'
import { api } from './helpers/api'

import { finish,session,start } from './helpers/study'

import type { WordGeneration } from '../../src/lib/dictionary-model'

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
  let saved = job
  await expect.poll(async () => { saved = (await api<WordGeneration>(page, `word-tasks/${job.task_id}`)).body; return saved.status }).toBe('SUCCEEDED')
  expect(saved.status).toBe('SUCCEEDED'); expect(saved.stage).toBe('READY')
  const word = (await api<{ senses: { id: number; examples: { content: string }[] }[] }>(page, `words/${saved.word_id}`)).body
  expect(word.senses[0].examples.map(example => example.content)).toEqual(['Ships dock at the [jetty].'])
  await expect(page.getByText('Ships dock at the jetty.', { exact: true })).toBeVisible()
  expect(await page.locator('t').count()).toBe(0)
  const deck = await nodes.create({ type: 'DECK', sense_ids: [word.senses[0].id] })
  const prepared = page.waitForResponse(r => r.url().endsWith('/study:prepare'))
  await start(page, deck.id)
  expect((await (await prepared).json()).actual_question_count).toBe(profile.settings.learning.questions_per_sense)
  await finish(page, profile.id)
  await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
  expect((await session(page, profile.id))!.receipt!.results).toHaveLength(1)
})
