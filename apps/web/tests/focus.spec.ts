import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { parseMarkedText } from '../src/lib/marked-text'
import { createMockServices } from '../src/lib/services/mock'
import database from '../src/lib/services/mock/database.json' with { type: 'json' }
import { advanceSession, createStudySession, currentQuestion, beginAttempt, diagnosticComplete, finishSession, recordAttempt, sessionKey, startNextRound } from '../src/lib/study-session'

const signal = new AbortController().signal

test('preparation supports every selected public type, one format and K up to three', async () => {
  const services = createMockServices({ latency: 0 })
  const types = services.account.initialProfile!.settings.learning.question_types
  for (const type of types) {
    await services.account.updateSettings({ learning: { question_types: [type], formats: ['SINGLE_CHOICE'], questions_per_sense: 3, max_sense_count: 1 } }, signal)
    const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
    expect(prepared.actual_question_count).toBe(3)
    for (const item of prepared.bundles[0].questions) {
      expect(item.question.question_type).toBe(type)
      expect(item.options).toHaveLength(4)
      expect(new Set(item.options.map(option => option.id)).size).toBe(4)
    }
  }
  await expect(services.learning.prepare({ node_id: 'everyday', selection: 'NEW', max_sense_count: 21 }, signal)).rejects.toMatchObject({ status: 422 })
})

test('retry recovery preserves the initial diagnostics and duplicated artifact occurrences', async () => {
  const services = createMockServices({ latency: 0 })
  await services.account.updateSettings({ learning: { question_types: ['DEFINITION_TO_WORD'], formats: ['SINGLE_CHOICE'], questions_per_sense: 2, max_sense_count: 1 } }, signal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  prepared.bundles[0].questions[1] = structuredClone(prepared.bundles[0].questions[0])
  let session = createStudySession('preview-alex', prepared)
  const firstOccurrence = session.questions[0]
  session = advanceSession(recordAttempt(beginAttempt(session, null), { correct: false }))
  session = advanceSession(recordAttempt(beginAttempt(session, currentQuestion(session)!.question.correct.id), { correct: true }))
  expect(session.phase).toBe('recap')
  session = startNextRound(session)
  expect(session.questions).toEqual([firstOccurrence])
  session = advanceSession(recordAttempt(beginAttempt(session, currentQuestion(session)!.question.correct.id), { correct: true }))
  expect(session.phase).toBe('submitting')
  expect(session.submission!.results).toHaveLength(2)
  expect(session.submission!.results.map(result => result.diagnostics)).toContainEqual({ correct: false })
  expect(session.submission!.results.map(result => result.diagnostics)).toContainEqual({ correct: true })
  const accepted = await services.learning.review(session.submission!, signal)
  expect(await services.learning.review(session.submission!, signal)).toEqual(accepted)
})

test('a grading failure keeps its locked answer and time without using a practice attempt', async () => {
  const services = createMockServices({ latency: 0 })
  await services.account.updateSettings({ learning: { question_types: ['DEFINITION_TO_WORD'], formats: ['SINGLE_WORD'], questions_per_sense: 1, max_sense_count: 1 } }, signal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  const locked = beginAttempt(createStudySession('preview-alex', prepared), 'bank', new Date('2026-10-11T00:00:00Z'))
  expect(beginAttempt(locked, 'a different answer')).toEqual(locked)
  expect(locked.attempts).toEqual({})
  const graded = recordAttempt(locked, { task_fit: true, spelling_error: false, sense_id: 999 })
  expect(graded.attempts[graded.questions[0]][0]).toMatchObject({ answer: 'bank', answered_at: '2026-10-11T00:00:00.000Z', complete: true })
  expect(finishSession(graded).submission!.results[0].diagnostics).toMatchObject({ sense_id: 999 })
})

test('only two retries are allowed and partial completion submits completed initial evidence', async () => {
  const services = createMockServices({ latency: 0 })
  await services.account.updateSettings({ learning: { question_types: ['DEFINITION_TO_WORD'], formats: ['SINGLE_CHOICE'], questions_per_sense: 1, max_sense_count: 1 } }, signal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  let session = createStudySession('preview-alex', prepared)
  for (let attempt = 0; attempt < 3; attempt++) {
    session = advanceSession(recordAttempt(beginAttempt(session, null), { correct: false }))
    if (attempt < 2) session = startNextRound(session)
  }
  expect(session.phase).toBe('submitting')
  expect(Object.values(session.attempts)[0]).toHaveLength(3)
  expect(session.submission!.results).toHaveLength(1)
  expect(session.submission!.results[0]).not.toHaveProperty('answer')
  expect(diagnosticComplete({ task_fit: true, spelling_error: true, sense_id: 1 })).toBe(false)
})

test('Pro preview renders single word and short answer questions', async ({ page }) => {
  const services = createMockServices({ latency: 0 })
  await page.goto('/focus/learn?node=everyday&selection=DUE')
  for (const [type, format, label, image] of [
    ['DEFINITION_TO_WORD', 'SINGLE_WORD', 'Your word', 'focus-single-word-desktop.png'],
    ['WORD_TO_DEFINITION', 'SHORT_ANSWER', 'Your answer', 'focus-short-answer-desktop.png'],
  ] as const) {
    await services.account.updateSettings({ learning: { question_types: [type], formats: [format], questions_per_sense: 1, max_sense_count: 1 } }, signal)
    const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'DUE' }, signal)
    expect(prepared.bundles[0].questions[0].format).toBe(format)
    const session = createStudySession('preview-alex', prepared)
    await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), { key: sessionKey('preview-alex', 'everyday'), value: session })
    await page.reload()
    await expect(page.getByRole('textbox', { name: label })).toBeVisible()
    mkdirSync('../../.impeccable/review', { recursive: true })
    await page.screenshot({ path: `../../.impeccable/review/${image}`, fullPage: true })
  }
})

test('round recap preserves the initial miss in the completed fullscreen quiz', async ({ page }) => {
  const services = createMockServices({ latency: 0 })
  await services.account.updateSettings({ learning: { questions_per_sense: 1, max_sense_count: 1 } }, signal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  const first = createStudySession('preview-alex', prepared)
  const recap = advanceSession(recordAttempt(beginAttempt(first, null), { correct: false }))
  const correct = currentQuestion(first)!
  await page.addInitScript(({ key, value }) => {
    if (sessionStorage.getItem('focus-test-seeded')) return
    localStorage.setItem(key, JSON.stringify(value)); sessionStorage.setItem('focus-test-seeded', '1')
  }, { key: sessionKey('preview-alex', 'everyday'), value: recap })
  await page.goto('/focus/learn?node=everyday&selection=NEW')
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
  await page.goto('/focus/learn?node=everyday&selection=NEW')
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
  mkdirSync('../../.impeccable/review', { recursive: true })
  await page.screenshot({ path: '../../.impeccable/review/focus-quiz-desktop.png', fullPage: true })
  await page.goto('/focus/flashcards?node=everyday')
  await expect(page.getByRole('article', { name: /Flashcard for/ })).toBeVisible()
  await expect(page.locator('.shell-desktop')).toHaveCount(0)
  await page.screenshot({ path: '../../.impeccable/review/focus-flashcards-desktop.png', fullPage: true })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/focus/learn?node=everyday&selection=NEW')
  await expect(page.locator('.focus-card')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
  const verticalGap = await page.locator('.focus-card-body').evaluate(node => node.getBoundingClientRect().top - node.parentElement!.getBoundingClientRect().top)
  expect(verticalGap).toBeLessThan(60)
  await page.screenshot({ path: '../../.impeccable/review/focus-quiz-mobile.png', fullPage: true })
  await page.setViewportSize({ width: 320, height: 700 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320)
  expect(errors).toEqual([])
})
