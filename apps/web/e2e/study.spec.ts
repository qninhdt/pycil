import { randomUUID } from 'node:crypto'
import { test, proTest, expect, api } from './fixtures'
import { currentQuestion } from '../src/lib/study-session'
import { session, start, finish } from './study-session'
import type { PreparedSession, QuestionType, StudyActivity, StudySummary, ReviewBatchResult } from '../src/lib/home-api'

const kinds: QuestionType[] = ['DEFINITION_TO_WORD', 'CONTEXT_TO_WORD', 'CLOZE_TO_WORD', 'WORD_TO_DEFINITION', 'WORD_TO_USAGE', 'DIALOGUE_COMPLETION', 'MEANING_IN_CONTEXT']
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
    await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
    expect(requests.filter(url => url.endsWith('/study:grade'))).toEqual([])
    expect(requests.filter(url => url.endsWith('/study:submitReviews'))).toHaveLength(1)
    const result = (await session(page, profile.id))!
    expect(result.receipt!.results).toHaveLength(1)
    expect(result.receipt!.results[0]).toMatchObject({ sense_id: 3 + index, applied: true })
    expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body).toMatchObject({ total: 1, studied: 1, new: 0 })
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('unknown answers retry, cap rating, preserve shuffled questions on reload and save once per sense', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [10] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { questions_per_sense: 2, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id, 'NEW')
    const before = await session(page, profile.id)
    await page.reload()
    await expect(page.getByRole('button', { name: 'Check answer', exact: true })).toBeVisible()
    expect(await session(page, profile.id)).toEqual(before)
    await finish(page, profile.id, true)
    await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
    const saved = (await session(page, profile.id))!
    expect(saved.round).toBeGreaterThan(1)
    expect(saved.receipt!.results).toHaveLength(1)
    expect(['AGAIN', 'HARD']).toContain(saved.receipt!.results[0].rating)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('empty and unready banks stay honest; NEW and DUE obey scope and maximum preferences', async ({ page, nodes, profile }) => {
  const unready = await nodes.create({ type: 'DECK', sense_ids: [100] })
  await page.goto(`/focus/learn?node=${unready.id}`)
  await page.getByRole('button', { name: 'Start session', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: 'No eligible questions' })).toBeVisible()
  const deck = await nodes.create({ type: 'DECK', sense_ids: [11, 12] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { max_sense_count: 1 } })).status).toBe(200)
    const prepared = await api<PreparedSession>(page, 'study:prepare', 'POST', { node_id: deck.id, selection: 'NEW' })
    expect(prepared.status).toBe(200)
    expect(prepared.body.actual_sense_count).toBe(1)
    expect(prepared.body.bundles.every(bundle => bundle.reason === 'NEW')).toBe(true)
    const due = await api<PreparedSession>(page, 'study:prepare', 'POST', { node_id: deck.id, selection: 'DUE' })
    expect(due.body.bundles).toEqual([])
    const forbidden = await api(page, 'study:prepare', 'POST', { node_id: randomUUID(), selection: 'AUTO' })
    expect(forbidden.status).toBe(404)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('Review selects native overdue memory and Free entitlement rejects typed grading', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [29, 30] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { max_sense_count: 1, questions_per_sense: 1 } })).status).toBe(200)
    await start(page, deck.id, 'DUE')
    const saved = (await session(page, profile.id))!
    expect(saved.prepared.bundles).toHaveLength(1)
    expect(saved.prepared.bundles[0]).toMatchObject({ sense: { id: 30 }, reason: 'DUE' })
    const question = currentQuestion(saved)!
    expect((await api(page, 'study:grade', 'POST', { question_id: question.question.id, format: 'SHORT_ANSWER', answer: 'bank' })).status).toBe(403)
    await finish(page, profile.id)
    await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
    const summary = (await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body
    expect(summary).toMatchObject({ total: 2, new: 1, due: 0, not_due: 1 })
    await page.goto(`/app/personal/${deck.id}/words`)
    await page.getByRole('radio', { name: /^New, / }).click()
    await expect(page.getByRole('button', { name: /View bank:.*fixture meaning 29$/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /^View / })).toHaveCount(1)
    await page.getByRole('radio', { name: /^Not yet due, / }).click()
    await expect(page.getByRole('button', { name: /View bank:.*fixture meaning 30$/ })).toBeVisible()
    await expect(page.getByRole('button', { name: /^View / })).toHaveCount(1)
    await page.getByRole('radio', { name: /^Due, / }).click()
    await expect(page.getByText('No matching words.', { exact: true })).toBeVisible()
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('unfinished scopes offer Resume and Discard; competing tabs cannot overwrite an answer', async ({ page, profile, nodes }) => {
  const first = await nodes.create({ type: 'DECK', sense_ids: [13] })
  const second = await nodes.create({ type: 'DECK', sense_ids: [14] })
  await start(page, first.id)
  const saved = await session(page, profile.id)
  await page.goto(`/focus/learn?node=${second.id}`)
  await expect(page.getByRole('heading', { name: 'Session in progress' })).toBeVisible()
  await page.getByRole('button', { name: 'Resume session' }).click()
  await expect(page).toHaveURL(new RegExp(`node=${first.id}`))
  expect(await session(page, profile.id)).toEqual(saved)
  const other = await page.context().newPage()
  try {
    await other.goto(page.url())
    await expect(other.getByRole('button', { name: 'Check answer', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'I don’t know', exact: true }).click()
    await other.getByRole('button', { name: 'I don’t know', exact: true }).click()
    await expect(other.getByRole('alert').filter({ hasText: 'changed in another tab' })).toBeVisible()
    expect((await session(page, profile.id))!.attempts).toEqual((await session(other, profile.id))!.attempts)
  } finally { await other.close() }
  await page.goto(`/focus/learn?node=${second.id}`)
  await page.getByRole('button', { name: 'Discard and start here' }).click()
  await page.getByRole('button', { name: 'Start session', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Check answer', exact: true })).toBeVisible()
  expect((await session(page, profile.id))!.prepared.node_id).toBe(second.id)
})

test('accepted review with lost response reloads the frozen batch and replays without duplicate activity', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [15] })
  const date = new Date().toISOString().slice(0, 10)
  const activityPath = `study/activity?start_date=${date}&end_date=${date}`
  const before = (await api<StudyActivity>(page, activityPath)).body
  let original: { body: string; key: string; receipt: ReviewBatchResult } | undefined
  await page.route('**/api/v1/study:submitReviews', async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    original = { body: route.request().postData()!, key: route.request().headers()['idempotency-key'], receipt: await response.json() }
    await route.abort('connectionfailed')
  }, { times: 1 })
  await start(page, deck.id, 'NEW')
  await finish(page, profile.id)
  await expect(page.getByRole('button', { name: 'Retry the same submission' })).toBeVisible()
  expect((await session(page, profile.id))!.phase).toBe('submitting')
  const replay = page.waitForRequest(request => request.url().endsWith('/study:submitReviews'))
  await page.reload()
  const request = await replay
  expect(request.postData()).toBe(original!.body)
  expect(request.headers()['idempotency-key']).toBe(original!.key)
  await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
  expect((await session(page, profile.id))!.receipt).toEqual(original!.receipt)
  const after = (await api<StudyActivity>(page, activityPath)).body
  expect(after.applied_events).toBe(before.applied_events + 1)
  const conflict = await api(page, 'study:submitReviews', 'POST', { results: [{ sense_id: 15, rating: 'AGAIN' }] }, true, { 'Idempotency-Key': original!.key })
  expect(conflict.status).toBe(409)
  const practice = await api<ReviewBatchResult>(page, 'study:submitReviews', 'POST', { results: [{ sense_id: 15, rating: 'GOOD' }] }, true, { 'Idempotency-Key': randomUUID() })
  expect(practice.body.results[0]).toMatchObject({ applied: false, due_after: original!.receipt.results[0].due_after })
  const practiced = (await api<StudyActivity>(page, activityPath)).body
  expect(practiced.practice_events).toBe(after.practice_events + 1)
})

for (const [index, format, kind] of [[0, 'SINGLE_WORD', 'DEFINITION_TO_WORD'], [1, 'SHORT_ANSWER', 'WORD_TO_DEFINITION']] as const) proTest(`native ${format} grades typed drafts, preserves reload and caps exhausted attempts`, async ({ page, profile, nodes }) => {
  const id = 16 + index
  const deck = await nodes.create({ type: 'DECK', sense_ids: [id] })
  try {
    expect((await api(page, 'study:submitReviews', 'POST', { results: [{ sense_id: id, rating: 'GOOD' }] }, true, { 'Idempotency-Key': randomUUID() })).status).toBe(200)
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: [kind], formats: [format], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id)
    expect(currentQuestion((await session(page, profile.id))!)!.format).toBe(format)
    const field = page.getByRole('textbox', { name: format === 'SINGLE_WORD' ? 'Your word' : 'Your answer' })
    await field.fill('my saved draft')
    const saved = await session(page, profile.id)
    await page.reload()
    await expect(field).toHaveValue('my saved draft')
    expect(await session(page, profile.id)).toEqual(saved)
    const graded = page.waitForResponse(r => r.url().endsWith('/study:grade'))
    await finish(page, profile.id, false, 'unrelated')
    expect((await graded).status()).toBe(200)
    await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
    const result = (await session(page, profile.id))!
    expect(Object.values(result.attempts)[0]).toHaveLength(3)
    expect(Object.values(result.attempts)[0][0].grade).not.toBeNull()
    expect(result.receipt!.results[0].rating).toBe('AGAIN')
    expect((await api(page, 'study:grade', 'POST', { question_id: 2147483647, format, answer: 'bank' })).status).toBe(404)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

proTest('a stale question rejected by native grading retains the draft and cannot submit a review', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [27] })
  try {
    expect((await api(page, 'study:submitReviews', 'POST', { results: [{ sense_id: 27, rating: 'GOOD' }] }, true, { 'Idempotency-Key': randomUUID() })).status).toBe(200)
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: ['WORD_TO_DEFINITION'], formats: ['SHORT_ANSWER'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id)
    const field = page.getByRole('textbox', { name: 'Your answer', exact: true })
    await field.fill('a place to keep money')
    const before = (await session(page, profile.id))!
    await page.route('**/api/v1/study:grade', route => route.continue({ postData: JSON.stringify({ ...route.request().postDataJSON(), question_id: 2147483647 }) }), { times: 1 })
    const graded = page.waitForResponse(r => r.url().endsWith('/study:grade'))
    let writes = 0
    page.on('request', r => { if (r.url().endsWith('/study:submitReviews')) writes++ })
    await page.getByRole('button', { name: 'Check answer', exact: true }).click()
    expect((await graded).status()).toBe(404)
    await expect(page.getByRole('alert').filter({ hasText: 'This question can no longer be graded with your current plan or question bank.' })).toBeVisible()
    await expect(field).toHaveValue('a place to keep money')
    expect((await session(page, profile.id))!.attempts).toEqual(before.attempts)
    expect(writes).toBe(0)
    await page.getByRole('button', { name: 'Start a new session', exact: true }).click()
    await page.getByRole('button', { name: 'Start session', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Check answer', exact: true })).toBeVisible()
    await finish(page, profile.id)
    await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
    expect(writes).toBe(1)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})
