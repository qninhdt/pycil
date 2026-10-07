import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { createMockServices } from '../src/lib/services/mock'
import database from '../src/lib/services/mock/database.json' with { type: 'json' }
import { advanceSession, createStudySession, currentQuestion, gradeOutcome, ratingForSense, recordAttempt, sessionKey, startNextRound } from '../src/lib/study-session'

const signal = new AbortController().signal

test('Pro preview includes both typed formats in review and keeps new questions multiple choice', async () => {
  const services = createMockServices({ latency: 0 })
  expect(services.account.initialProfile).toMatchObject({ plan: 'pro', learning_options: { advanced_grading: true } })
  const due = await services.learning.prepare({ node_id: 'everyday', selection: 'DUE' }, signal)
  const formats = due.bundles.flatMap(bundle => bundle.questions.map(item => item.format))
  expect(new Set(formats)).toEqual(new Set(['SINGLE_CHOICE', 'SINGLE_WORD', 'SHORT_ANSWER']))
  for (const bundle of due.bundles) {
    expect(bundle.questions.filter(item => item.format === 'SINGLE_WORD').length).toBeLessThanOrEqual(1)
    expect(bundle.questions.filter(item => item.format === 'SHORT_ANSWER').length).toBeLessThanOrEqual(1)
    for (const item of bundle.questions) expect(services.account.initialProfile!.learning_options.pairs).toContainEqual(expect.objectContaining({ question_type: item.question.question_type, format: item.format }))
  }
  const fresh = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  expect(fresh.actual_question_count).toBeGreaterThan(0)
  expect(fresh.bundles.every(bundle => bundle.questions.every(item => item.format === 'SINGLE_CHOICE'))).toBe(true)
})

test('mock preparation covers every question type with backend-shaped options', async () => {
  const services = createMockServices({ latency: 0 })
  const types = services.account.initialProfile!.settings.learning.question_types
  for (const type of types) {
    await services.account.updateSettings({ learning: { question_types: [type], questions_per_sense: 7, max_sense_count: 1 } }, signal)
    const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
    expect(prepared.actual_question_count).toBe(7)
    expect(prepared.bundles[0].questions).toHaveLength(7)
    for (const item of prepared.bundles[0].questions) {
      expect(item.question.question_type).toBe(type)
      expect(item.options).toHaveLength(4)
      expect(new Set(item.options.map(option => option.id)).size).toBe(4)
      expect(item.options.some(option => option.id === item.question.correct.id)).toBe(true)
      if (type === 'MEANING_IN_CONTEXT') expect(item.question.content).toMatch(/<t\b[^>]*>.+?<\/t>/)
      if (type === 'DIALOGUE_COMPLETION' && item.question.target_placement === 'OPTIONS') {
        const targets = item.options.map(option => option.content.match(/<t\b[^>]*>(.*?)<\/t>/)?.[1])
        expect(new Set(targets).size).toBe(1)
        expect(targets[0]).toBeTruthy()
      }
    }
  }
  const sample = structuredClone(database)
  const senseIds = sample.dictionary.words.flatMap(word => word.senses.map(sense => sense.id))
  sample.library.membership.everyday = senseIds
  sample.library.new_sense_ids = senseIds
  sample.library.due_sense_ids = []
  const fullBank = createMockServices({ database: sample, latency: 0 })
  for (const type of types) {
    await fullBank.account.updateSettings({ learning: { question_types: [type], questions_per_sense: 1, max_sense_count: 80 } }, signal)
    const prepared = await fullBank.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
    expect(prepared.bundles.map(bundle => bundle.sense.id).sort((a, b) => a - b)).toEqual([...senseIds].sort((a, b) => a - b))
    expect(prepared.bundles.every(bundle => bundle.questions[0].question.question_type === type)).toBe(true)
    if (type === 'MEANING_IN_CONTEXT') expect(prepared.bundles.every(bundle => /<t\b[^>]*>.+?<\/t>/.test(bundle.questions[0].question.content as string))).toBe(true)
  }
})

test('a missed question returns next round and caps the sense at Hard after recovery', async () => {
  const services = createMockServices({ latency: 0 })
  await services.account.updateSettings({ learning: { questions_per_sense: 3, max_sense_count: 1 } }, signal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  let session = createStudySession('preview-alex', prepared)
  const first = currentQuestion(session)!
  session = recordAttempt(session, first.question.distractors[0].id, null)
  session = advanceSession(session)
  for (let index = 1; index < 3; index++) {
    const item = currentQuestion(session)!
    session = advanceSession(recordAttempt(session, item.question.correct.id, null))
  }
  expect(session.phase).toBe('recap')
  session = startNextRound(session)
  expect(currentQuestion(session)?.question.id).toBe(first.question.id)
  session = advanceSession(recordAttempt(session, first.question.correct.id, null))
  expect(session.phase).toBe('submitting')
  expect(ratingForSense(session, prepared.bundles[0].sense.id)).toBe('HARD')
  const accepted = await services.learning.review(session.submission!, signal)
  expect(accepted.results).toHaveLength(1)
  expect(await services.learning.review(session.submission!, signal)).toEqual(accepted)
})

test('mock typed grading uses the native result fields for word, definition and usage', async () => {
  const sample = structuredClone(database)
  const services = createMockServices({ database: sample, latency: 0 })
  for (const [type, format] of [
    ['DEFINITION_TO_WORD', 'SINGLE_WORD'], ['WORD_TO_DEFINITION', 'SHORT_ANSWER'], ['WORD_TO_USAGE', 'SHORT_ANSWER'],
  ] as const) {
    await services.account.updateSettings({ learning: { question_types: [type], formats: [format], questions_per_sense: 1, max_sense_count: 1 } }, signal)
    const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
    const bundle = prepared.bundles[0], item = bundle.questions[0]
    const lemma = sample.dictionary.words.find(word => word.id === bundle.sense.word_id)!.lemma
    const definition = bundle.sense.definition!.content
    const answer = type === 'DEFINITION_TO_WORD' ? lemma : type === 'WORD_TO_DEFINITION' ? definition : `${lemma} — ${definition} in a real situation.`
    const grade = await services.learning.grade({ question_id: item.question.id, format, answer }, signal)
    expect(gradeOutcome(item, answer, grade)).toBe('clear')
    if (format === 'SINGLE_WORD') {
      const typo = lemma.slice(0, -1)
      const partial = await services.learning.grade({ question_id: item.question.id, format, answer: typo }, signal)
      expect(partial).toMatchObject({ task_fit: true, spelling_error: true, sense_id: null })
      expect(gradeOutcome(item, typo, partial)).toBe('partial')
    }
  }
  sample.library.membership.everyday = [53]
  sample.library.new_sense_ids = [53]
  sample.library.due_sense_ids = []
  const cloze = createMockServices({ database: sample, latency: 0 })
  await cloze.account.updateSettings({ learning: { question_types: ['CLOZE_TO_WORD'], formats: ['SINGLE_WORD'], questions_per_sense: 2, max_sense_count: 1 } }, signal)
  const prepared = await cloze.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  const inflected = prepared.bundles[0].questions[1]
  expect(inflected.question.correct.content).toBe('running')
  const reopened = createMockServices({ database: sample, latency: 0 })
  const graded = await reopened.learning.grade({ question_id: inflected.question.id, format: 'SINGLE_WORD', answer: 'running' }, signal)
  expect(gradeOutcome(inflected, 'running', graded)).toBe('clear')
})

test('three misses produce Again, while a typed draft survives a browser reload', async ({ page }) => {
  const sample = structuredClone(database)
  const services = createMockServices({ database: sample, latency: 0 })
  await services.account.updateSettings({ learning: { question_types: ['DEFINITION_TO_WORD'], formats: ['SINGLE_WORD'], questions_per_sense: 1, max_sense_count: 1 } }, signal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  let session = createStudySession('preview-alex', prepared)
  for (let attempt = 0; attempt < 3; attempt++) {
    session = advanceSession(recordAttempt(session, '', null, true))
    if (attempt < 2) session = startNextRound(session)
  }
  expect(session.phase).toBe('submitting')
  expect(session.submission?.results).toEqual([{ sense_id: prepared.bundles[0].sense.id, rating: 'AGAIN' }])

  const draft = { ...createStudySession('preview-alex', prepared), draft: 'an unfinished answer' }
  await page.addInitScript(({ key, value }) => {
    if (sessionStorage.getItem('focus-test-seeded')) return
    localStorage.setItem(key, JSON.stringify(value))
    sessionStorage.setItem('focus-test-seeded', '1')
  }, { key: sessionKey('preview-alex'), value: draft })
  await page.goto('/focus/learn?node=everyday&selection=NEW')
  await expect(page.getByRole('textbox', { name: 'Your word' })).toHaveValue('an unfinished answer')
  await page.reload()
  await expect(page.getByRole('textbox', { name: 'Your word' })).toHaveValue('an unfinished answer')
  await page.getByRole('button', { name: 'Check answer' }).click()
  await expect(page.locator('.focus-feedback')).toBeVisible()
  await expect(page.locator('.focus-feedback')).toContainText('Try this again next round.')
  await page.goto('/focus/learn?node=everyday&selection=DUE')
  await expect(page.getByRole('heading', { name: 'Session in progress' })).toBeVisible()
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
    await page.evaluate(({ key, value }) => localStorage.setItem(key, JSON.stringify(value)), { key: sessionKey('preview-alex'), value: session })
    await page.reload()
    await expect(page.getByRole('textbox', { name: label })).toBeVisible()
    mkdirSync('../../.impeccable/review', { recursive: true })
    await page.screenshot({ path: `../../.impeccable/review/${image}`, fullPage: true })
  }
})

test('round recap advances to an applied final rating in the fullscreen quiz', async ({ page }) => {
  const services = createMockServices({ latency: 0 })
  await services.account.updateSettings({ learning: { questions_per_sense: 1, max_sense_count: 1 } }, signal)
  const prepared = await services.learning.prepare({ node_id: 'everyday', selection: 'NEW' }, signal)
  const first = createStudySession('preview-alex', prepared)
  const recap = advanceSession(recordAttempt(first, '', null, true))
  const correct = currentQuestion(first)!
  await page.addInitScript(({ key, value }) => {
    if (sessionStorage.getItem('focus-test-seeded')) return
    localStorage.setItem(key, JSON.stringify(value)); sessionStorage.setItem('focus-test-seeded', '1')
  }, { key: sessionKey('preview-alex'), value: recap })
  await page.goto('/focus/learn?node=everyday&selection=NEW')
  await expect(page.getByText('Ready for another pass.')).toBeVisible()
  await expect(page.getByText('1', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: 'Continue to round 2' }).click()
  await page.locator('.focus-options button').nth(correct.options.findIndex(option => option.id === correct.question.correct.id)).click()
  await page.getByRole('button', { name: 'Check answer' }).click()
  await page.getByRole('button', { name: 'Continue', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Session complete.' })).toBeVisible()
  await expect(page.getByText('1 meaning reviewed.')).toBeVisible()
  await page.getByText('See ratings by meaning').click()
  await expect(page.getByText('Review schedule updated')).toBeVisible()
})

test('quiz keeps the same question after reload and flashcards open without the sidebar', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/focus/learn?node=everyday&selection=NEW')
  await page.getByRole('button', { name: 'Start session' }).click()
  await expect(page.locator('.focus-card')).toBeVisible()
  const prompt = await page.locator('.focus-card h1').textContent()
  await page.reload()
  await expect(page.locator('.focus-card h1')).toHaveText(prompt!)
  await page.locator('.focus-options button').first().click()
  await page.getByRole('button', { name: 'Check answer' }).click()
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
