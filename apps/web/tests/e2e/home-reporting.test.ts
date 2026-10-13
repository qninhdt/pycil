import { expect,test } from './fixtures'
import { api } from './helpers/api'

import { randomUUID } from 'node:crypto'

import type { PreparedSession,ReviewBatchResult,ReviewSchedule,StudyActivity,StudySummary } from '../../src/lib/home-api'

function summaryLabel({ due, new: fresh, not_due, total }: StudySummary) {
  return `${due} due, ${fresh} new, ${not_due} not yet due; ${total} total meanings`
}

test('Home reports deduplicated native counts, practice activity, timezone and schedule without reviews on navigation', async ({ page, profile, nodes }) => {
  const first = await nodes.create({ type: 'deck', sense_ids: [18, 19] })
  expect((await api<StudySummary>(page, `study/progress?node_id=${first.id}`)).body.total).toBe(2)
  const beforeDuplicate = (await api<StudySummary>(page, 'study/progress')).body
  const practiced = await nodes.create({ type: 'deck', sense_ids: [18] })
  const afterDuplicate = (await api<StudySummary>(page, 'study/progress')).body
  expect(afterDuplicate).toMatchObject({ total: beforeDuplicate.total, new: beforeDuplicate.new,
    studied: beforeDuplicate.studied, due: beforeDuplicate.due, not_due: beforeDuplicate.not_due })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { timezone: 'Pacific/Kiritimati' })).status).toBe(200)
    const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Pacific/Kiritimati', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
    const before = (await api<StudyActivity>(page, `study/activity?start_date=${date}&end_date=${date}`)).body
    const streak = before.current_streak + (before.days[0].applied_events + before.days[0].practice_events > 0 ? 0 : 1)
    const prepared = await api<PreparedSession>(page, 'study:prepare', 'POST', { node_id: practiced.id, selection: 'auto' })
    expect(prepared.status).toBe(200)
    const question = prepared.body.bundles[0].questions[0]
    const answeredAt = new Date().toISOString()
    for (let attempt = 0; attempt < 2; attempt++) {
      const answerTime = attempt === 0 ? answeredAt : new Date(Date.parse(answeredAt) - 1000).toISOString()
      const result = await api<ReviewBatchResult>(page, 'study:submitResults', 'POST', { results: [{ question_artifact_id: question.question.question_artifact_id, question_type: question.question.question_type, format: question.format, diagnostics: { correct: true }, answered_at: answerTime }] }, true, { 'Idempotency-Key': randomUUID() })
      expect(result.status).toBe(200)
      expect(result.body.results[0].applied).toBe(attempt === 0)
    }
    const activity = (await api<StudyActivity>(page, `study/activity?start_date=${date}&end_date=${date}`)).body
    const summary = (await api<StudySummary>(page, 'study/progress')).body
    expect(summary).toMatchObject({ total: 2, new: 1, studied: 1, not_due: 1 })
    expect(activity).toMatchObject({ timezone: 'Pacific/Kiritimati', current_streak: streak,
      applied_events: before.applied_events + 1, practice_events: before.practice_events + 1 })
    const schedule = (await api<ReviewSchedule>(page, `study/review-schedule?start_date=${date}&end_date=${date}`)).body
    expect(schedule.timezone).toBe('Pacific/Kiritimati')
    expect(schedule.days).toHaveLength(1)
    const writes: string[] = []
    page.on('request', r => { if (r.url().endsWith('/study:submitResults')) writes.push(r.url()) })
    await page.goto('/app')
    await expect(page.getByRole('img', { name: summaryLabel(summary) })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Study streak' }).getByText(String(streak), { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('region', { name: 'Study activity' })).toBeVisible()
    expect(writes).toEqual([])
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('Home API outage shows an error and retry restores backend counts without preview data', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'deck', sense_ids: [20] })
  const summary = (await api<StudySummary>(page, 'study/progress')).body
  expect(profile.id).toBeTruthy(); expect(deck.id).toBeTruthy()
  await page.route('**/v1/study/progress*', route => route.abort('connectionfailed'))
  await page.goto('/app')
  const today = page.getByRole('region', { name: 'Today', exact: true })
  await expect(today.getByText('Could not load Library counts.', { exact: true })).toBeVisible()
  await page.unroute('**/v1/study/progress*')
  await today.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('img', { name: summaryLabel(summary) })).toBeVisible()
})
