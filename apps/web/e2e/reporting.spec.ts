import { test, expect, api } from './fixtures'
import { randomUUID } from 'node:crypto'
import { finish } from './study-session'
import type { StudyActivity, StudySummary, ReviewSchedule } from '../src/lib/home-api'

test('Home reports deduplicated native counts, practice activity, timezone and schedule without reviews on navigation', async ({ page, profile, nodes }) => {
  await nodes.create({ type: 'DECK', sense_ids: [18, 19] })
  await nodes.create({ type: 'DECK', sense_ids: [18] })
  try {
    expect((await api(page, 'me/settings', 'PATCH', { timezone: 'Pacific/Kiritimati' })).status).toBe(200)
    expect((await api(page, 'study:submitReviews', 'POST', { results: [{ sense_id: 18, rating: 'GOOD' }] }, true, { 'Idempotency-Key': randomUUID() })).status).toBe(200)
    expect((await api(page, 'study:submitReviews', 'POST', { results: [{ sense_id: 18, rating: 'GOOD' }] }, true, { 'Idempotency-Key': randomUUID() })).status).toBe(200)
    const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Pacific/Kiritimati', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
    const activity = (await api<StudyActivity>(page, `study/activity?start_date=${date}&end_date=${date}`)).body
    const summary = (await api<StudySummary>(page, 'study/progress')).body
    expect(summary).toMatchObject({ total: 2, new: 1, studied: 1, not_due: 1 })
    expect(activity).toMatchObject({ timezone: 'Pacific/Kiritimati', current_streak: 1 })
    expect(activity.practice_events).toBeGreaterThanOrEqual(1)
    const schedule = (await api<ReviewSchedule>(page, `study/review-schedule?start_date=${date}&end_date=${date}`)).body
    expect(schedule.timezone).toBe('Pacific/Kiritimati')
    expect(schedule.days).toHaveLength(1)
    const writes: string[] = []
    page.on('request', r => { if (r.url().endsWith('/study:submitReviews')) writes.push(r.url()) })
    await page.goto('/app')
    await expect(page.getByRole('img', { name: '0 due, 1 new, 1 not yet due; 2 total meanings' })).toBeVisible()
    await expect(page.getByRole('region', { name: 'Study streak' }).getByText('1', { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('region', { name: 'Study activity' })).toBeVisible()
    expect(writes).toEqual([])
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('Home API outage shows an error and retry restores backend counts without preview data', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [20] })
  expect(profile.id).toBeTruthy(); expect(deck.id).toBeTruthy()
  await page.route('**/api/v1/study/progress*', route => route.abort('connectionfailed'))
  await page.goto('/app')
  const today = page.getByRole('region', { name: 'Today', exact: true })
  await expect(today.getByText('Could not load Library counts.', { exact: true })).toBeVisible()
  await page.unroute('**/api/v1/study/progress*')
  await today.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.getByRole('img', { name: '0 due, 1 new, 0 not yet due; 1 total meanings' })).toBeVisible()
})

test.describe('mobile', () => {
  test.use({ viewport: { width: 390, height: 844 } })

test('mobile real login, deck creation, native meanings and learning preserve accessible navigation', async ({ page, profile, nodes }) => {
  const name = 'mobile-' + randomUUID()
  await page.goto('/app/personal?create=deck')
  const form = page.getByRole('dialog', { name: 'New deck' })
  await form.getByRole('textbox', { name: 'Title' }).fill(name)
  const created = page.waitForResponse(r => r.url().endsWith('/api/v1/nodes') && r.request().method() === 'POST')
  await form.getByRole('button', { name: 'Create deck', exact: true }).click()
  const deck = await (await created).json(); nodes.track(deck.id)
  await page.getByRole('tab', { name: 'Words', exact: true }).click()
  await page.getByRole('button', { name: 'Add words', exact: true }).click()
  const picker = page.getByRole('dialog', { name: 'Add words to deck' })
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('bank')
  await picker.getByRole('checkbox').first().check()
  await picker.getByRole('button', { name: 'Add to deck', exact: true }).click()
  await expect(picker).not.toBeVisible()
  await page.getByRole('button', { name: /^View bank:/ }).click()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: /^View bank:/ })).toBeFocused()
  await page.goto(`/focus/learn?node=${deck.id}&selection=AUTO`)
  await page.getByRole('button', { name: 'Start session', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Check answer', exact: true })).toBeVisible()
  await page.keyboard.press('1')
  await expect(page.locator('.focus-options button').first()).toHaveAttribute('aria-pressed', 'true')
  expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.total).toBe(1)
  await finish(page, profile.id)
  await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
  expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.studied).toBe(1)
})
})
