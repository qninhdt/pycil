import { expect,proTest,test } from './fixtures'
import { api } from './helpers/api'

import { finish,session,start } from './helpers/study'

import type { ReviewBatchResult,StudyActivity,StudySummary } from '../../src/lib/home-api'

import { randomUUID } from 'node:crypto'

test('cold question bank exposes a provider rejection in a popup, retries generation and completes learning', async ({ page, profile, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  await nodes.create({ type: 'DECK', parent_id: folder.id, sense_ids: [32] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: ['DEFINITION_TO_WORD'], formats: ['SINGLE_CHOICE'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    await page.goto(`/app/personal/${folder.id}`)
    const prepare = page.waitForResponse(response => response.url().endsWith('/study:prepare'))
    await page.getByRole('link', { name: /^Learn new/ }).click()
    const failure = await prepare
    expect(failure.status()).toBe(503)
    expect(await failure.json()).toEqual({ error: 'question_generation_unavailable' })
    const popup = page.getByRole('alertdialog')
    await expect(popup).toContainText('Questions could not be generated right now.')
    expect(await session(page, profile.id, folder.id)).toBeNull()
    await popup.getByRole('button', { name: 'Retry', exact: true }).click()
    await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
    await finish(page, profile.id)
    await expect(page.getByRole('heading', { name: 'Session complete', exact: true })).toBeVisible()
    expect((await api<StudySummary>(page, `study/progress?node_id=${folder.id}`)).body.studied).toBe(1)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('empty and missing scopes show recoverable popups inside focus rather than a fullscreen error page', async ({ page, profile, nodes }) => {
  const empty = await nodes.create({ type: 'DECK' })
  await page.goto(`/focus/learn?node=${empty.id}&selection=NEW`)
  const popup = page.getByRole('alertdialog')
  await expect(popup).toContainText('No eligible questions')
  expect(await session(page, profile.id, empty.id)).toBeNull()
  await popup.getByRole('button', { name: 'Back to My Library' }).click()
  await expect(page).toHaveURL(new RegExp(`/app/personal/${empty.id}$`))
  await page.goto('/focus/learn?node=00000000-0000-0000-0000-000000000000')
  await expect(popup).toContainText('This material could not be found.')
  await expect(page.getByRole('button', { name: 'Exit learning mode', includeHidden: true })).toBeVisible()
})

test('leaving delayed preparation cannot create a local session or submit a review', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [27] })
  let release!: () => void, reached!: () => void
  const held = new Promise<void>(resolve => { release = resolve })
  const requested = new Promise<void>(resolve => { reached = resolve })
  const writes: string[] = []
  page.on('request', request => { if (request.url().endsWith('/study:submitResults')) writes.push(request.url()) })
  await page.route('**/api/v1/study:prepare', async route => {
    const response = await route.fetch()
    reached()
    await held
    await route.fulfill({ response }).catch(() => {})
  })
  try {
    await page.goto(`/focus/learn?node=${deck.id}`)
    await requested
    await page.getByRole('button', { name: 'Exit learning mode' }).click()
    await expect(page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
    release()
    expect(await session(page, profile.id, deck.id)).toBeNull()
    expect(writes).toEqual([])
    expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.studied).toBe(0)
  } finally { release() }
})

for (const corrupt of ['broken JSON', 'outdated shape']) test(`${corrupt} in local study storage is replaced by a real prepared session`, async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [25] })
  await page.evaluate(({ id, node, corrupt }) => {
    localStorage.setItem(`pycil:study:${id}:${node}`, corrupt === 'broken JSON' ? '{' : JSON.stringify({ version: 2, accountId: id, prepared: { node_id: node, bundles: [] }, questions: [] }))
  }, { id: profile.id, node: deck.id, corrupt })
  await page.goto(`/focus/learn?node=${deck.id}`)
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  await expect(page.getByRole('alertdialog')).toHaveCount(0)
  expect((await session(page, profile.id, deck.id))!.prepared.actual_question_count).toBeGreaterThan(0)
})

test('blocked study storage shows a popup and cannot silently lose a session', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [24] })
  await page.addInitScript(() => {
    const native = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key.startsWith('pycil:study:') && !(window as unknown as { allowStudyStorage: boolean }).allowStudyStorage) throw new DOMException('Study storage is full', 'QuotaExceededError')
      return native.call(this, key, value)
    }
  })
  await page.goto(`/focus/learn?node=${deck.id}`)
  const popup = page.getByRole('alertdialog')
  await expect(popup).toContainText('This browser cannot save the session.')
  expect(await session(page, profile.id, deck.id)).toBeNull()
  await page.evaluate(() => { (window as unknown as { allowStudyStorage: boolean }).allowStudyStorage = true })
  await popup.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  expect((await session(page, profile.id, deck.id))!.prepared.node_id).toBe(deck.id)
})

test('pause resumes the same answered question; partial finish saves only attempted evidence once', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [22, 23] })
  await page.goto(`/focus/learn?node=${deck.id}`)
  await page.getByRole('button', { name: 'I don’t know', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeVisible()
  const before = await session(page, profile.id, deck.id)
  await page.getByRole('button', { name: 'Exit learning mode' }).click()
  const popup = page.getByRole('alertdialog')
  await popup.getByRole('button', { name: 'Pause & exit' }).click()
  await expect(page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
  expect(await session(page, profile.id, deck.id)).toEqual(before)
  await page.getByRole('link', { name: /^Practice/ }).click()
  await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeVisible()
  expect(await session(page, profile.id, deck.id)).toEqual(before)
  const submissions: string[] = []
  page.on('request', request => { if (request.url().endsWith('/study:submitResults')) submissions.push(request.url()) })
  await page.getByRole('button', { name: 'Exit learning mode' }).click()
  await popup.getByRole('button', { name: 'Finish & save' }).click()
  await expect(page.getByRole('heading', { name: 'Session complete', exact: true })).toBeVisible()
  expect(submissions).toHaveLength(1)
  expect((await session(page, profile.id, deck.id))!.receipt!.evidence).toHaveLength(1)
  expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.studied).toBe(1)
})

test('unknown answers retry, preserve initial diagnostics and save once per sense', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [26] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { questions_per_sense: 2, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id, 'NEW')
    const before = await session(page, profile.id)
    await page.reload()
    await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
    expect(await session(page, profile.id)).toEqual(before)
    await finish(page, profile.id, true)
    await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
    const saved = (await session(page, profile.id))!
    expect(saved.round).toBeGreaterThan(1)
    expect(saved.receipt!.results).toHaveLength(1)
    expect(saved.receipt!.evidence.some(result => 'correct' in result.diagnostics && !result.diagnostics.correct)).toBe(true)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('each node maintains independent session; competing tabs cannot overwrite an answer', async ({ page, profile, nodes }) => {
  const first = await nodes.create({ type: 'DECK', sense_ids: [13] })
  const second = await nodes.create({ type: 'DECK', sense_ids: [14] })
  await start(page, first.id)
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  const savedFirst = await session(page, profile.id, first.id)
  expect(savedFirst).not.toBeNull()

  // Opening another node starts an independent session without blocker modals
  await start(page, second.id)
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  const savedSecond = await session(page, profile.id, second.id)
  expect(savedSecond).not.toBeNull()
  expect(savedSecond!.prepared.node_id).toBe(second.id)

  // Returning to first node restores its independent session
  await page.goto(`/focus/learn?node=${first.id}`)
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  const restoredFirst = await session(page, profile.id, first.id)
  expect(restoredFirst).not.toBeNull()
  expect(restoredFirst!.prepared.node_id).toBe(first.id)

  const other = await page.context().newPage()
  try {
    await other.goto(page.url())
    await expect(other.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'I don’t know', exact: true }).click()
    await other.getByRole('button', { name: 'I don’t know', exact: true }).click()
    await expect(other.getByRole('alert').filter({ hasText: 'changed in another tab' })).toBeVisible()
    expect((await session(page, profile.id, first.id))!.attempts).toEqual((await session(other, profile.id, first.id))!.attempts)
  } finally { await other.close() }
})

test('accepted review with lost response reloads the frozen batch and replays without duplicate activity', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [15] })
  const date = new Date().toISOString().slice(0, 10)
  const activityPath = `study/activity?start_date=${date}&end_date=${date}`
  const before = (await api<StudyActivity>(page, activityPath)).body
  let original: { body: string; key: string; receipt: ReviewBatchResult } | undefined
  await page.route('**/api/v1/study:submitResults', async route => {
    const response = await route.fetch()
    expect(response.status()).toBe(200)
    original = { body: route.request().postData()!, key: route.request().headers()['idempotency-key'], receipt: await response.json() }
    await route.abort('connectionfailed')
  }, { times: 1 })
  await start(page, deck.id, 'NEW')
  await finish(page, profile.id)
  await expect(page.getByRole('button', { name: 'Retry the same submission' })).toBeVisible()
  expect((await session(page, profile.id))!.phase).toBe('submitting')
  const replay = page.waitForRequest(request => request.url().endsWith('/study:submitResults'))
  await page.reload()
  const request = await replay
  expect(request.postData()).toBe(original!.body)
  expect(request.headers()['idempotency-key']).toBe(original!.key)
  await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
  expect((await session(page, profile.id))!.receipt).toEqual(original!.receipt)
  const after = (await api<StudyActivity>(page, activityPath)).body
  expect(after.applied_events).toBe(before.applied_events + 1)
  const originalBody = JSON.parse(original!.body)
  const changed = structuredClone(originalBody)
  changed.results[0].diagnostics = { correct: !changed.results[0].diagnostics.correct }
  const conflict = await api(page, 'study:submitResults', 'POST', changed, true, { 'Idempotency-Key': original!.key })
  expect(conflict.status).toBe(409)
  const practice = await api<ReviewBatchResult>(page, 'study:submitResults', 'POST', originalBody, true, { 'Idempotency-Key': randomUUID() })
  expect(practice.status).toBe(200)
  expect(practice.body.results[0].elo).toBeCloseTo(original!.receipt.results[0].elo)

})

proTest('a stale question rejected by native grading retains the draft and cannot submit a review', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [27] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: ['WORD_TO_DEFINITION'], formats: ['SHORT_ANSWER'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id)
    const field = page.getByRole('textbox', { name: 'Your answer', exact: true })
    await field.fill('a place to keep money')
    const before = (await session(page, profile.id))!
    await page.route('**/api/v1/study:grade', route => route.continue({ postData: JSON.stringify({ ...route.request().postDataJSON(), question_artifact_id: 2147483647 }) }), { times: 1 })
    const graded = page.waitForResponse(r => r.url().endsWith('/study:grade'))
    let writes = 0
    page.on('request', r => { if (r.url().endsWith('/study:submitResults')) writes++ })
    await page.getByRole('button', { name: 'Check answer', exact: true }).click()
    expect((await graded).status()).toBe(404)
    await expect(page.getByRole('alert').filter({ hasText: 'This question can no longer be graded with your current plan or question bank.' })).toBeVisible()
    await expect(field).toHaveValue('a place to keep money')
    expect((await session(page, profile.id))!.attempts).toEqual(before.attempts)
    expect(writes).toBe(0)
    await page.getByRole('button', { name: 'Start a new session', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Check answer', exact: true })).toBeVisible()
    await finish(page, profile.id)
    await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
    expect(writes).toBe(1)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

proTest('a lost native grading response preserves the locked answer across reload and retry consumes one attempt', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [26] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { learning: { question_types: ['WORD_TO_DEFINITION'], formats: ['SHORT_ANSWER'], questions_per_sense: 1, max_sense_count: 1 } })).status).toBe(200)
    await start(page, deck.id)
    const field = page.getByRole('textbox', { name: 'Your answer', exact: true })
    await field.fill('my answer survives a lost response')
    let firstBody: unknown
    await page.route('**/api/v1/study:grade', async route => {
      firstBody = route.request().postDataJSON()
      expect((await route.fetch()).status()).toBe(200)
      await route.abort('connectionfailed')
    }, { times: 1 })
    await page.getByRole('button', { name: 'Check answer', exact: true }).click()
    await expect(page.getByRole('button', { name: 'Retry grading', exact: true })).toBeVisible()
    const locked = (await session(page, profile.id, deck.id))!
    expect(locked.pendingAttempt?.answer).toBe('my answer survives a lost response')
    expect(locked.attempts).toEqual({})
    await page.reload()
    await expect(field).toHaveValue('my answer survives a lost response')
    await expect(field).toBeDisabled()
    expect((await session(page, profile.id, deck.id))!.pendingAttempt).toEqual(locked.pendingAttempt)
    const request = page.waitForRequest(request => request.url().endsWith('/study:grade'))
    await page.getByRole('button', { name: 'Retry grading', exact: true }).click()
    expect((await request).postDataJSON()).toEqual(firstBody)
    await expect(page.getByRole('button', { name: 'Continue', exact: true })).toBeVisible()
    const saved = (await session(page, profile.id, deck.id))!
    expect(saved.pendingAttempt).toBeNull()
    expect(Object.values(saved.attempts)[0]).toHaveLength(1)
    expect(Object.values(saved.attempts)[0][0].answered_at).toBe(locked.pendingAttempt!.answered_at)
    expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.studied).toBe(0)
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})
