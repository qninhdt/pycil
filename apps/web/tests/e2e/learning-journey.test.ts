import { expect,test } from './fixtures'
import { api } from './helpers/api'

import { randomUUID } from 'node:crypto'

import { finish } from './helpers/study'

import type { StudySummary } from '../../src/lib/home-api'

test('guest landing actions and unknown routes remain usable without exposing private data', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('link', { name: /Get started|Start learning|Sign up/i }).first()).toBeVisible()
  expect((await api(page, 'me', 'GET', undefined, false)).status).toBe(401)
  await page.goto('/a-page-that-does-not-exist')
  await expect(page.getByRole('heading', { name: 'This page isn’t here.', exact: true })).toBeVisible()
  await page.getByRole('link', { name: /Return.*Home/i }).click()
  await expect(page).toHaveURL(/\/app$/)
})

test.describe('mobile', () => {
  test.use({ viewport: { width: 390, height: 844 } })

test('mobile real login, deck creation, native meanings and learning preserve accessible navigation', async ({ page, profile, nodes }) => {
  const name = 'mobile-' + randomUUID()
  await page.goto('/app/personal?create=deck')
  const form = page.getByRole('dialog', { name: 'New deck' })
  await form.getByRole('textbox', { name: 'Title' }).fill(name)
  const created = page.waitForResponse(r => r.url().endsWith('/v1/nodes') && r.request().method() === 'POST')
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
  await page.getByRole('tab', { name: 'Overview', exact: true }).click()
  await page.getByRole('link', { name: /^Practice,/ }).click()
  await expect(page).toHaveURL(new RegExp(`/app/learn\\?node=${deck.id}&selection=auto`))
  await expect(page.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
  await page.keyboard.press('1')
  await expect(page.locator('.focus-feedback')).toBeVisible()
  expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.total).toBe(1)
  await finish(page, profile.id)
  await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
  expect((await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body.studied).toBe(1)
  await page.goto(`/app/personal/${deck.id}/words`)
  await page.reload()
  await expect(page.locator('.library-state-cell')).toHaveText('Not yet due')
  const progress = (await api<StudySummary>(page, 'study/progress')).body
  await page.goto('/app')
  await page.reload()
  await expect(page.getByRole('img', { name: `${progress.due} due, ${progress.new} new, ${progress.not_due} not yet due; ${progress.total} total meanings`, exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name, exact: true })).toBeVisible()

})
})
