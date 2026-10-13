import { expect,test } from '@playwright/test'
import { preparation } from '../../unit/fixtures'
import { accountPlatform,navigationPlatform } from './fixtures/api-fixtures'
import { buildFixture,renderFixture } from './fixtures/render-fixture'


import { createMockServices } from '../../../src/lib/api/services/mock'

import { advanceSession,beginAttempt,createStudySession,currentQuestion,recordAttempt,sessionKey } from '../../../src/features/study/session'

const focusSignal = new AbortController().signal

test('HTTP study renders native single word and short answer question formats', async ({ page }) => {
  const bundle = await buildFixture('study', { '@/features/account/account.client': accountPlatform, 'next/navigation': navigationPlatform })
  for (const [type, format, label] of [
    ['definition_to_word', 'single_word', 'Your word'],
    ['word_to_definition', 'short_answer', 'Your answer'],
  ] as const) {
    const prepared = preparation(1, format)
    prepared.bundles[0].questions[0].question.question_type = type
    prepared.preferences.question_types = [type]
    let calls = 0
    await page.goto('/app')
    await page.evaluate(() => localStorage.clear())
    await page.route('**/*v1/**', route => {
      const path = new URL(route.request().url()).pathname
      if (path.endsWith('/study:prepare')) { calls++; return route.fulfill({ json: prepared }) }
      if (path.endsWith('/words:batchPreview')) return route.fulfill({ json: [{ word_id: 1, lemma: 'bank', entry_type: 'word', senses: [prepared.bundles[0].sense] }] })
      throw new Error(`Unexpected native study request: ${path}`)
    })
    await renderFixture(page, bundle, 'study', '?node=deck&selection=new')
    await expect(page.getByRole('textbox', { name: label })).toBeVisible()
    await page.reload()
    await expect(page.getByRole('textbox', { name: label })).toBeVisible()
    expect(calls).toBe(1)
    await page.unroute('**/*v1/**')
  }
})

test('round recap preserves the initial miss in the completed fullscreen quiz', async ({ page }) => {
  const services = createMockServices({ latency: 0 })
  await services.account.updateSettings({ learning: { questions_per_sense: 1, max_sense_count: 1 } }, focusSignal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'new' }, focusSignal)
  const first = createStudySession('preview-alex', prepared)
  const recap = advanceSession(recordAttempt(beginAttempt(first, null), { correct: false }))
  const correct = currentQuestion(first)!
  await page.addInitScript(({ key, value }) => {
    if (sessionStorage.getItem('focus-test-seeded')) return
    localStorage.setItem(key, JSON.stringify(value)); sessionStorage.setItem('focus-test-seeded', '1')
  }, { key: sessionKey('preview-alex', 'everyday'), value: recap })
  await page.goto('/app/learn?node=everyday&selection=new')
  await expect(page.getByText('Ready for another pass.')).toBeVisible()
  await expect(page.getByText('1', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Continue to round 2' }).click()
  await page.locator('.focus-options button').nth(correct.options.findIndex(option => option.id === correct.question.correct.id)).click()
  if (await page.getByRole('button', { name: 'Check answer' }).isVisible()) {
    await page.getByRole('button', { name: 'Check answer' }).click()
  }
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Session complete' })).toBeVisible()
  await expect(page.getByText('1 meaning reviewed.')).toBeVisible()
  await page.getByText('See mastery by meaning').click()
  await expect(page.getByText('Review schedule updated')).toBeVisible()
})

test('quiz keeps the same question after reload and flashcards open without the sidebar', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/app/learn?node=everyday&selection=new')
  await expect(page.locator('.focus-card')).toBeVisible()
  const prompt = await page.locator('.focus-card h1').textContent()
  await page.reload()
  await expect(page.locator('.focus-card h1')).toHaveText(prompt!)
  await page.locator('.focus-options button').first().click()
  if (await page.getByRole('button', { name: 'Check answer' }).isVisible()) {
    await page.getByRole('button', { name: 'Check answer' }).click()
  }
  await expect(page.locator('.focus-feedback')).toBeVisible()
  await page.reload()
  await expect(page.locator('.focus-feedback')).toBeVisible()
  await page.goto('/app/flashcards?node=everyday')
  await expect(page.getByRole('article', { name: /Flashcard for/ })).toBeVisible()
  await expect(page.locator('.shell-desktop')).toHaveCount(0)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/app/learn?node=everyday&selection=new')
  await expect(page.locator('.focus-card')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  const verticalGap = await page.locator('.focus-card-body').evaluate(node => node.getBoundingClientRect().top - node.parentElement!.getBoundingClientRect().top)
  expect(verticalGap).toBeLessThan(60)
  await page.setViewportSize({ width: 320, height: 700 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  expect(errors).toEqual([])
})

test('Study actions route to fullscreen focus mode without preparing questions on Library', async ({ page }) => {
  const studyRequests: string[] = []
  page.on('request', request => { if (request.url().includes('/v1/study')) studyRequests.push(request.url()) })
  await page.goto('/app/personal/business-core')
  await expect(page.getByRole('heading', { name: 'Deck details' })).toBeVisible()
  const preview = page.getByRole('region', { name: 'Flashcard preview' })
  await expect(preview.locator('article[data-face=front]')).toBeVisible()
  await expect(page.getByRole('link', { name: /^Flashcards,/ })).toHaveAttribute('href', '/app/flashcards?node=business-core')
  await expect(page.getByRole('link', { name: /^Learn new,/ })).toHaveAttribute('href', '/app/learn?node=business-core&selection=new')
  await page.getByRole('link', { name: /^Practice,/ }).click()
  await expect(page).toHaveURL(/\/app\/learn\?node=business-core&selection=auto$/)
  await expect(page.getByRole('button', { name: 'Exit learning mode' })).toBeVisible()
  await expect(page.locator('.shell-desktop, .library-inline-preview, .home-session')).toHaveCount(0)
  expect(studyRequests).toEqual([])
})

test('HTTP study preparation failure stays in focus and exposes an accessible retry popup', async ({ page }) => {
  const bundle = await buildFixture('study', { '@/features/account/account.client': accountPlatform, 'next/navigation': navigationPlatform })
  let preparations = 0
  await page.route('**/*v1/**', route => {
    expect(new URL(route.request().url()).pathname.endsWith('/study:prepare')).toBe(true)
    expect(route.request().method()).toBe('POST')
    expect(route.request().headers().authorization).toBe('Bearer test-only-bearer')
    expect(route.request().postDataJSON().node_id).toBe('http-deck')
    preparations++
    return route.fulfill({ status: 503, json: { error: 'question_generation_unavailable' } })
  })
  await renderFixture(page, bundle, 'study', '?node=http-deck&selection=new')
  const popup = page.getByRole('alertdialog')
  await expect(popup).toBeVisible()
  await expect(popup).toContainText('Questions could not be generated')
  await popup.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect.poll(() => preparations).toBe(2)
  await expect(popup).toBeVisible()
  expect(await page.evaluate(() => Object.keys(localStorage).filter(key => key.startsWith('pycil:study:')))).toEqual([])
})
