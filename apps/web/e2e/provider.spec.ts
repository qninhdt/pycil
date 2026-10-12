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

  test('real generation normalizes an inflected input into its lemma', async ({ page, profile }) => {
    test.setTimeout(720000)
    expect(profile.id).toBeTruthy()
    const hits = (await api<{ items: { kind: string; reference_id?: string; display?: string }[] }>(page, 'words:search?query=glistening&include_reference=true')).body.items
    const reference = hits.find(hit => hit.kind === 'REFERENCE' && hit.display === 'glistening')!
    expect(reference).toBeTruthy()
    const generated = await api<WordGeneration>(page, 'words:generate', 'POST', { reference_id: reference.reference_id, target: 'glistening' })
    expect(generated.status).toBe(202)
    await expect.poll(async () => (await api<WordGeneration>(page, generated.body.status_url.replace('/v1/', ''))).body.status, { timeout: 600000 }).toBe('SUCCEEDED')
    const task = (await api<WordGeneration>(page, `word-tasks/${generated.body.task_id}`)).body
    const word = (await api<DictionaryWord>(page, `words/${task.word_id}`)).body
    expect(word.lemma).toBe('glisten')
    expect(word.senses.length).toBeGreaterThan(0)
    const pastHits = (await api<{ items: { kind: string; reference_id?: string; display?: string }[] }>(page, 'words:search?query=glistened&include_reference=true')).body.items
    const past = pastHits.find(hit => hit.kind === 'REFERENCE' && hit.display === 'glistened')!
    expect(past).toBeTruthy()
    const reuse = await api<WordGeneration>(page, 'words:generate', 'POST', { reference_id: past.reference_id, target: 'glistened' })
    await expect.poll(async () => (await api<WordGeneration>(page, reuse.body.status_url.replace('/v1/', ''))).body.status, { timeout: 600000 }).toBe('SUCCEEDED')
    const reusedTask = (await api<WordGeneration>(page, `word-tasks/${reuse.body.task_id}`)).body
    expect(reusedTask.word_id).toBe(word.id)
    expect((await api<DictionaryWord>(page, `words/${word.id}`)).body).toEqual(word)
    const after = (await api<{ items: { kind: string; reference_id?: string }[] }>(page, 'words:search?query=glistened&include_reference=true')).body.items
    expect(after.some(hit => hit.reference_id === past.reference_id)).toBe(false)
  })

  test('real Assistant reads actual sense IDs and accepts another message', async ({ page, profile }) => {
    expect(profile.id).toBeTruthy()
    await openAssistant(page)
    const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
    const streamed = page.waitForResponse(r => r.url().endsWith('/assistant:run'))
    await page.getByRole('textbox', { name: 'Message PycilAI' }).fill('Use dictionary tools to find the saved word bank, read its senses, then check my learning state for those exact sense IDs. Keep your answer brief.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const conversation: Conversation = await (await created).json()
    try {
      const stream = await (await streamed).text()
      expect(stream).toMatch(/search_words|read_vocabulary/)
      expect(stream).toContain('RUN_FINISHED')
      expect(stream).not.toContain('RUN_ERROR')
      const next = page.waitForResponse(r => r.url().endsWith('/assistant:run'))
      await page.getByRole('textbox', { name: 'Message PycilAI' }).fill('Give one short example using the financial sense of bank.')
      await page.getByRole('button', { name: 'Send message', exact: true }).click()
      const reply = await (await next).text()
      expect(reply).toContain('RUN_FINISHED')
      expect(reply).not.toContain('RUN_ERROR')
      await expect(page.locator('.ai-message-error, .ai-error')).toHaveCount(0)
    } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
  })

  test('real generation produces native readable senses', async ({ page, profile, nodes }) => {
    test.setTimeout(720000)
    expect(profile.plan).toBe('PRO')
    await page.goto('/app/dictionary?q=harbor')
    await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText('Pro plan')
    await page.getByRole('button', { name: 'harbor Needs preparation Generate', exact: true }).click()
    const created = page.waitForResponse(r => r.url().endsWith('/words:generate') && r.request().method() === 'POST')
    await page.getByRole('button', { name: 'Prepare entry', exact: true }).click()
    const response = await created
    expect(response.status()).toBe(202)
    const job: WordGeneration = await response.json()
    let saved = job
    await expect.poll(async () => {
      saved = (await api<WordGeneration>(page, `word-tasks/${job.task_id}`)).body
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
      expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: ['WORD_TO_DEFINITION'], formats: ['SHORT_ANSWER'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
      await start(page, deck.id)
      const graded = page.waitForResponse(r => r.url().endsWith('/study:grade'), { timeout: 120000 })
      await finish(page, profile.id)
      expect((await graded).status()).toBe(200)
      await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
      expect((await session(page, profile.id))!.receipt!.results).toHaveLength(1)
    } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
  })

  test('real Assistant streams an answer and reopens checkpoint history', async ({ page, profile }) => {
    expect(profile.id).toBeTruthy()
    await openAssistant(page)
    const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
    const streamed = page.waitForResponse(r => r.url().endsWith('/assistant:run'), { timeout: 120000 })
    await page.getByRole('textbox', { name: 'Message PycilAI' }).fill('Reason through why ships float. Write approximately 800 words for a learner. Start your answer with: Pycil integration verified.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const conversation: Conversation = await (await created).json()
    try {
      const response = await streamed
      expect(response.status()).toBe(200)
      await expect(page.locator('.ai-markdown').last()).toContainText('Pycil integration verified.')
      const stream = await response.text()
      expect(stream).toContain('TEXT_MESSAGE_CONTENT')
      expect(stream).toContain('RUN_FINISHED')
      expect(stream).not.toContain('RUN_ERROR')
      const saved = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body
      expect(saved.state.messages.some(message => message.role === 'assistant' && typeof message.content === 'string' && message.content.length > 1000)).toBe(true)
      await expect(page.locator('.ai-message-error, .ai-error')).toHaveCount(0)
      await page.reload()
      await openAssistant(page)
      await expect(page.getByText(/Pycil integration verified/).last()).toBeVisible()
    } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
  })
})
