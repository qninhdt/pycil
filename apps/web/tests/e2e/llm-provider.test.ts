import { expect,proTest as test } from './fixtures'
import { api } from './helpers/api'

import { finish,session,start } from './helpers/study'

import type { Conversation,ConversationDetails } from '../../src/lib/assistant-api'

import type { DictionaryWord,WordGeneration } from '../../src/lib/dictionary-model'

import { parseMarkedText } from '../../src/lib/marked-text'

import { open as openAssistant } from './helpers/assistant'

test.describe('real LLM providers', { tag: '@live-provider' }, () => {
  test.setTimeout(240000)

  test('real generation normalizes an unambiguous inflected input into its lemma', async ({ page, profile }) => {
    test.setTimeout(720000)
    expect(profile.id).toBeTruthy()
    const hits = (await api<{ items: { kind: string; reference_id?: string; display?: string }[] }>(page, 'words:search?query=glistened&include_reference=true')).body.items
    const reference = hits.find(hit => hit.kind === 'reference' && hit.display === 'glistened')!
    expect(reference).toBeTruthy()
    const generated = await api<WordGeneration>(page, 'words:generate', 'POST', { reference_id: reference.reference_id, target: 'glistened' })
    expect(generated.status).toBe(202)
    await expect.poll(async () => {
      const status = (await api<WordGeneration>(page, generated.body.status_url.replace('/v1/', ''))).body.status
      return status === 'succeeded' || status === 'failed'
    }, { timeout: 600000 }).toBe(true)
    const task = (await api<WordGeneration>(page, `word-tasks/${generated.body.task_id}`)).body
    expect(task.status, `${task.stage}: ${task.error}`).toBe('succeeded')
    const word = (await api<DictionaryWord>(page, `words/${task.word_id}`)).body
    expect(word.lemma).toBe('glisten')
    expect(word.senses.length).toBeGreaterThan(0)
    const reuse = await api<WordGeneration>(page, 'words:generate', 'POST', { reference_id: reference.reference_id, target: 'glistened' })
    await expect.poll(async () => (await api<WordGeneration>(page, reuse.body.status_url.replace('/v1/', ''))).body.status, { timeout: 600000 }).toBe('succeeded')
    const reusedTask = (await api<WordGeneration>(page, `word-tasks/${reuse.body.task_id}`)).body
    expect(reusedTask.word_id).toBe(word.id)
    expect((await api<DictionaryWord>(page, `words/${word.id}`)).body).toEqual(word)
    const after = (await api<{ items: { kind: string; reference_id?: string }[] }>(page, 'words:search?query=glistened&include_reference=true')).body.items
    expect(after.some(hit => hit.reference_id === reference.reference_id)).toBe(false)
  })

  test('real Assistant reads actual sense IDs and accepts another message', async ({ page, profile, nodes }) => {
    expect(profile.id).toBeTruthy()
    const bank = await nodes.create({ type: 'deck', name: 'bank', sense_ids: [16, 17] })
    await openAssistant(page)
    const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
    const streamed = page.waitForResponse(r => r.url().endsWith('/assistant:run'))
    await page.getByRole('textbox', { name: 'Message PycilAI' }).fill(`Use search_nodes to find the deck named "${bank.name}" in my Library, then pass its exact node ID to read_library with content view. Briefly report the returned sense IDs and learning states.`)
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const conversation: Conversation = await (await created).json()
    try {
      const stream = await (await streamed).text()
      expect(stream).toContain('search_nodes')
      expect(stream).toContain('read_library')
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
    expect(profile.plan).toBe('pro')
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
      return ['succeeded', 'failed'].includes(saved.status)
    }, { timeout: 630000 }).toBe(true)
    expect(saved.status, `${saved.stage}: ${saved.error}`).toBe('succeeded')
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
    const deck = await nodes.create({ type: 'deck', sense_ids: word.body.senses.map(sense => sense.id) })
    try {
      expect((await api(page, 'me/settings', 'PATCH', { learning: { questions_per_sense: 1, max_sense_count: 1, formats: ['single_choice'] } })).status).toBe(200)
      await start(page, deck.id)
      await finish(page, profile.id)
      await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
      expect((await session(page, profile.id))!.receipt!.results).toHaveLength(1)
    } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
  })

  test('real typed grading completes a native session and persists its review', async ({ page, profile, nodes }) => {
    const deck = await nodes.create({ type: 'deck', sense_ids: [16] })
    try {
      expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: ['word_to_definition'], formats: ['short_answer'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
      await start(page, deck.id)
      const graded = page.waitForResponse(r => r.url().endsWith('/study:grade'), { timeout: 120000 })
      await finish(page, profile.id)
      expect((await graded).status()).toBe(200)
      await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
      expect((await session(page, profile.id))!.receipt!.results).toHaveLength(1)
    } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
  })

  test('real Assistant streams an answer and reopens checkpoint history', async ({ page, profile }) => {
    expect(profile.id).toBeTruthy()
    await openAssistant(page)
    const created = page.waitForResponse(r => r.url().endsWith('/assistant/conversations') && r.request().method() === 'POST')
    const streamed = page.waitForResponse(r => r.url().endsWith('/assistant:run'), { timeout: 120000 })
    await page.getByRole('textbox', { name: 'Message PycilAI' }).fill('Explain briefly why ships float for an English learner.')
    await page.getByRole('button', { name: 'Send message', exact: true }).click()
    const conversation: Conversation = await (await created).json()
    try {
      const response = await streamed
      expect(response.status()).toBe(200)
      const stream = await response.text()
      expect(stream).toContain('TEXT_MESSAGE_CONTENT')
      expect(stream).toContain('RUN_FINISHED')
      expect(stream).not.toContain('RUN_ERROR')
      const saved = (await api<ConversationDetails>(page, `assistant/conversations/${conversation.id}`)).body
      expect(saved.state.messages.some(message => message.role === 'assistant' && typeof message.content === 'string' && message.content.trim().length > 0)).toBe(true)
      await expect(page.locator('.ai-message-error, .ai-error')).toHaveCount(0)
      const answer = await page.locator('.ai-markdown').last().innerText()
      expect(answer.trim().length).toBeGreaterThan(0)
      await page.reload()
      await openAssistant(page)
      await expect(page.locator('.ai-markdown').last()).toHaveText(answer)
    } finally { expect((await api(page, `assistant/conversations/${conversation.id}`, 'DELETE')).status).toBe(204) }
  })
})
