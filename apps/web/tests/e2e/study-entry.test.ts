import { expect,test } from './fixtures'
import { api } from './helpers/api'

import { finish,session,start } from './helpers/study'

import type { StudySummary } from '../../src/lib/home-api'


import { currentQuestion } from '../../src/lib/study-session'

for (const [label, selection, width] of [['Learn new', 'NEW'], ['Practice', 'AUTO'], ['Learn new', 'NEW', 390], ['Practice', 'AUTO', 390]] as const) test(`${label} ${width ?? 1440}px enters focus directly; failed preparation opens a popup and retry loads real questions`, async ({ page, profile, nodes }) => {
  if (width) await page.setViewportSize({ width, height: 844 })
  const folder = await nodes.create({ type: 'FOLDER' })
  await nodes.create({ type: 'DECK', parent_id: folder.id, sense_ids: [28] })
  await page.goto(`/app/personal/${folder.id}`)
  await page.route('**/api/v1/study:prepare', route => route.abort('connectionfailed'), { times: 1 })
  const failed = page.waitForEvent('requestfailed', { predicate: request => request.url().endsWith('/study:prepare') })
  await page.getByRole('link', { name: new RegExp(`^${label}`) }).click()
  await failed
  await expect(page).toHaveURL(new RegExp(`/focus/learn\\?node=${folder.id}&selection=${selection}`))
  const popup = page.getByRole('alertdialog')
  await expect(popup).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Learn', exact: true })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Exit learning mode', includeHidden: true })).toBeVisible()
  expect(await session(page, profile.id, folder.id)).toBeNull()
  const prepared = page.waitForResponse(response => response.url().endsWith('/study:prepare'))
  await popup.getByRole('button', { name: 'Retry', exact: true }).click()
  expect((await prepared).status()).toBe(200)
  await expect(popup).not.toBeVisible()
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  expect((await session(page, profile.id, folder.id))!.prepared.selection).toBe(selection)
  expect((await api<StudySummary>(page, `study/progress?node_id=${folder.id}`)).body.studied).toBe(0)
})

test('cold generation works with saved defaults without a prefilled bank or learning writes', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [31] })
  await page.goto(`/app/personal/${deck.id}`)
  await page.getByRole('link', { name: /^Practice/ }).click()
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  const saved = (await session(page, profile.id, deck.id))!
  expect(saved.prepared.actual_question_count).toBe(profile.settings.learning.questions_per_sense)
  expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.studied).toBe(0)
})

test('Home study action navigates directly to focus without a second Start session action', async ({ page, profile, nodes }) => {
  await nodes.create({ type: 'DECK', sense_ids: [26] })
  await page.goto('/app')
  await page.getByRole('region', { name: 'Today', exact: true }).getByRole('link', { name: /Start review|Learn new|Practice/ }).first().click()
  await expect(page).toHaveURL(/\/focus\/learn\?node=/)
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Start session', exact: true })).toHaveCount(0)
  expect((await session(page, profile.id, profile.library_node_id))!.prepared.node_id).toBe(profile.library_node_id)
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
    expect((await api(page, 'study:grade', 'POST', { question_artifact_id: question.question.question_artifact_id, question_type: question.question.question_type, format: 'SHORT_ANSWER', answer: 'bank' })).status).toBe(403)
    await finish(page, profile.id)
    await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
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
