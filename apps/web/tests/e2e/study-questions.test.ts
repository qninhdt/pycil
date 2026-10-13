import { expect,proTest,test } from './fixtures'
import { api } from './helpers/api'

import { currentQuestion } from '../../src/lib/study-session'

import { finish,session,start } from './helpers/study'

import type { QuestionType,StudySummary } from '../../src/lib/home-api'

const kinds: QuestionType[] = ['definition_to_word', 'context_to_word', 'cloze_to_word', 'word_to_definition', 'word_to_usage', 'dialogue_completion', 'meaning_in_context', 'sentence_rewrite']

for (const [index, kind] of kinds.entries()) test(`native ${kind} renders, answers without grading and submits one review`, async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'deck', sense_ids: [3 + index] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: [kind], formats: ['single_choice'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    const requests: string[] = []
    page.on('request', request => { if (request.url().includes('/study:')) requests.push(request.url()) })
    await start(page, deck.id, 'new')
    const prepared = (await session(page, profile.id))!.prepared
    expect(prepared.bundles[0].questions[0].question.question_type).toBe(kind)
    expect(prepared.bundles[0].reason).toBe('new')
    expect(await page.locator('.focus-options button').count()).toBe(4)
    expect(await page.locator('t').count()).toBe(0)
    await finish(page, profile.id)
    await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
    expect(requests.filter(url => url.endsWith('/study:grade'))).toEqual([])
    expect(requests.filter(url => url.endsWith('/study:submitResults'))).toHaveLength(1)
    const result = (await session(page, profile.id))!
    expect(result.receipt!.results).toHaveLength(1)
    expect(result.receipt!.results[0]).toMatchObject({ sense_id: 3 + index, applied: true })
    expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body).toMatchObject({ total: 1, studied: 1, new: 0 })
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

for (const [index, format, kind] of [[0, 'single_word', 'definition_to_word'], [1, 'short_answer', 'word_to_definition'], [2, 'single_word', 'context_to_word'], [3, 'single_word', 'cloze_to_word'], [4, 'short_answer', 'word_to_usage'], [5, 'short_answer', 'sentence_rewrite']] as const) proTest(`native ${kind} ${format} grades typed drafts, preserves reload and caps exhausted attempts`, async ({ page, profile, nodes }) => {
  const id = 16 + index
  const deck = await nodes.create({ type: 'deck', sense_ids: [id] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: [kind], formats: [format], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id)
    expect(currentQuestion((await session(page, profile.id))!)!.format).toBe(format)
    const field = page.getByRole('textbox', { name: format === 'single_word' ? 'Your word' : kind === 'sentence_rewrite' ? 'Your rewrite' : 'Your answer' })
    await field.fill('my saved draft')
    const saved = await session(page, profile.id)
    await page.reload()
    await expect(field).toHaveValue('my saved draft')
    expect(await session(page, profile.id)).toEqual(saved)
    const graded = page.waitForResponse(r => r.url().endsWith('/study:grade'))
    await finish(page, profile.id, false, 'unrelated')
    expect((await graded).status()).toBe(200)
    await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
    const result = (await session(page, profile.id))!
    expect(Object.values(result.attempts)[0]).toHaveLength(3)
    expect(Object.values(result.attempts)[0][0]).toBeDefined()
    expect(result.receipt!.evidence[0].recall).toBe(kind === 'word_to_usage' ? null : 0)
    expect(result.receipt!.evidence[0].performance).toBe(kind === 'sentence_rewrite' ? null : 0)
    expect((await api(page, 'study:grade', 'POST', { question_artifact_id: 2147483647, question_type: kind, format, answer: 'bank' })).status).toBe(404)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})
