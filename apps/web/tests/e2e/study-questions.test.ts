import { expect,proTest,test } from './fixtures'
import { api } from './helpers/api'

import { currentQuestion } from '../../src/lib/study-session'

import { finish,session,start } from './helpers/study'

import type { QuestionType,StudySummary } from '../../src/lib/home-api'

const kinds: QuestionType[] = ['DEFINITION_TO_WORD', 'CONTEXT_TO_WORD', 'CLOZE_TO_WORD', 'WORD_TO_DEFINITION', 'WORD_TO_USAGE', 'DIALOGUE_COMPLETION', 'MEANING_IN_CONTEXT', 'SENTENCE_REWRITE']

for (const [index, kind] of kinds.entries()) test(`native ${kind} renders, answers without grading and submits one review`, async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [3 + index] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: [kind], formats: ['SINGLE_CHOICE'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    const requests: string[] = []
    page.on('request', request => { if (request.url().includes('/study:')) requests.push(request.url()) })
    await start(page, deck.id, 'NEW')
    const prepared = (await session(page, profile.id))!.prepared
    expect(prepared.bundles[0].questions[0].question.question_type).toBe(kind)
    expect(prepared.bundles[0].reason).toBe('NEW')
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

for (const [index, format, kind] of [[0, 'SINGLE_WORD', 'DEFINITION_TO_WORD'], [1, 'SHORT_ANSWER', 'WORD_TO_DEFINITION'], [2, 'SINGLE_WORD', 'CONTEXT_TO_WORD'], [3, 'SINGLE_WORD', 'CLOZE_TO_WORD'], [4, 'SHORT_ANSWER', 'WORD_TO_USAGE'], [5, 'SHORT_ANSWER', 'SENTENCE_REWRITE']] as const) proTest(`native ${kind} ${format} grades typed drafts, preserves reload and caps exhausted attempts`, async ({ page, profile, nodes }) => {
  const id = 16 + index
  const deck = await nodes.create({ type: 'DECK', sense_ids: [id] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: [kind], formats: [format], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id)
    expect(currentQuestion((await session(page, profile.id))!)!.format).toBe(format)
    const field = page.getByRole('textbox', { name: format === 'SINGLE_WORD' ? 'Your word' : kind === 'SENTENCE_REWRITE' ? 'Your rewrite' : 'Your answer' })
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
    expect(result.receipt!.evidence[0].recall).toBe(kind === 'WORD_TO_USAGE' ? null : 0)
    expect(result.receipt!.evidence[0].performance).toBe(kind === 'SENTENCE_REWRITE' ? null : 0)
    expect((await api(page, 'study:grade', 'POST', { question_artifact_id: 2147483647, question_type: kind, format, answer: 'bank' })).status).toBe(404)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})
