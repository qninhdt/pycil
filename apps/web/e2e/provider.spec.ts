import { randomUUID } from 'node:crypto'
import { proTest as test, expect, api } from './fixtures'
import { start, finish, session } from './study-session'
import type { Conversation, ConversationDetails } from '../src/lib/assistant-api'
import type { WordGeneration, DictionaryWord } from '../src/lib/dictionary-model'
import { parseMarkedText } from '../src/lib/marked-text'

async function openAssistant(page: import('@playwright/test').Page) {
  const panel = page.getByRole('complementary', { name: 'PycilAI', exact: true })
  const launcher = page.getByRole('button', { name: 'Open PycilAI', exact: true })
  await expect.poll(async () => await panel.isVisible() || await launcher.isVisible()).toBe(true)
  if (!await panel.isVisible()) await launcher.click()
  await expect(page.getByRole('textbox', { name: 'Message PycilAI' })).toBeVisible()
}

test.describe('live external providers', () => {
  test.skip(process.env.E2E_PROVIDER_PROFILE !== 'live', 'Run the separate live provider profile with configured inference and decision services.')
  test.setTimeout(240000)

  test('real generation reaches the worker and produces native readable senses', async ({ page, profile, nodes }) => {
    test.setTimeout(720000)
    expect(profile.plan).toBe('PRO')
    await page.goto('/app/dictionary?q=harbor')
    await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText('Pro plan')
    await page.getByRole('button', { name: 'harbor Needs preparation', exact: true }).click()
    const created = page.waitForResponse(r => r.url().endsWith('/word-generations') && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Prepare entry', exact: true }).click()
    const response = await created
    expect(response.status()).toBe(202)
    const job: WordGeneration = await response.json()
    let saved = job
    await expect.poll(async () => {
      saved = (await api<WordGeneration>(page, `word-generations/${job.generation_id}`)).body
      return ['SUCCEEDED', 'FAILED'].includes(saved.status)
    }, { timeout: 630000 }).toBe(true)
    expect(saved.status, `${saved.stage}: ${saved.error}`).toBe('SUCCEEDED')
    await expect(page.getByRole('heading', { name: 'harbor', exact: true })).toBeVisible()
    const word = await api<DictionaryWord>(page, `words/${saved.word_id}`)
    expect(word.status).toBe(200)
    expect(word.body.senses.length).toBeGreaterThan(0)
    console.info(`Live generation: ${saved.stage}; senses: ${word.body.senses.length}`)
    for (const sense of word.body.senses) {
      expect(sense.examples.length).toBeGreaterThan(0)
      for (const example of sense.examples) {
        const parsed = parseMarkedText(example.content)
        expect(parsed.valid).toBe(true); expect(parsed.spans.length).toBeGreaterThan(0)
      }
    }
    const deck = await nodes.create({ type: 'DECK', sense_ids: word.body.senses.map(sense => sense.id) })
    try {
      expect((await api(page, 'me/settings', 'PATCH', { learning: { questions_per_sense: 1, max_sense_count: 1, formats: ['SINGLE_CHOICE'] } })).status).toBe(200)
      await start(page, deck.id)
      await finish(page, profile.id)
      await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
      expect((await session(page, profile.id))!.receipt!.results).toHaveLength(1)
    } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
  })

  test('real typed grading completes a native session and persists its review', async ({ page, profile, nodes }) => {
    const deck = await nodes.create({ type: 'DECK', sense_ids: [16] })
    try {
      expect((await api(page, 'study:submitReviews', 'POST', { results: [{ sense_id: 16, rating: 'GOOD' }] }, true, { 'Idempotency-Key': randomUUID() })).status).toBe(200)
      expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: ['WORD_TO_DEFINITION'], formats: ['SHORT_ANSWER'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
      await start(page, deck.id)
      const graded = page.waitForResponse(r => r.url().endsWith('/study:grade'), { timeout: 120000 })
      await finish(page, profile.id)
      expect((await graded).status()).toBe(200)
      await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
      expect((await session(page, profile.id))!.receipt!.results).toHaveLength(1)
    } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
  })

  test('real Assistant streams reasoning and a long answer before completion; checkpoint history reopens', async ({ page, profile }) => {
    expect(profile.id).toBeTruthy()
    await openAssistant(page)
    let completed = false
    page.on('requestfinished', request => { if (request.url().endsWith('/assistant:run')) completed = true })
    const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
    const streamed = page.waitForResponse(r => r.url().endsWith('/assistant:run'), { timeout: 120000 })
    await page.getByRole('textbox', { name: 'Message PycilAI' }).fill('Reason through why ships float. Write approximately 800 words for a learner. Start your answer with: Pycil integration verified.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const conversation: Conversation = await (await created).json()
    try {
      const response = await streamed
      expect(response.status()).toBe(200)
      await expect(page.locator('.ai-reasoning-body')).toBeVisible()
      expect(completed).toBe(false)
      await expect(page.locator('.ai-markdown').last()).toContainText('Pycil integration verified.')
      expect(completed).toBe(false)
      const stream = await response.text()
      expect(stream).toContain('RUN_FINISHED')
      expect(stream).not.toContain('RUN_ERROR')
      const saved = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body
      expect(saved.state.messages.some(message => message.role === 'reasoning' && message.content)).toBe(true)
      expect(saved.state.messages.some(message => message.role === 'assistant' && typeof message.content === 'string' && message.content.length > 1000)).toBe(true)
      await expect(page.locator('.ai-message-error, .ai-error')).toHaveCount(0)
      await page.reload()
      await openAssistant(page)
      await expect(page.getByText(/Pycil integration verified/).last()).toBeVisible()
    } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
  })
})
