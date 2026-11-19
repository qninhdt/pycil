import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { answerChoice, finishStudy, selectQuestions, startStudy } from '../../support/study.ts'

test('a learner submits a choice and records study progress', async ({ user, data, vocabulary }) => {
  await selectQuestions(user, 'definition_to_word')
  const deck = await data.create({ name: 'Choice exercise', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
})

test('a typed lexical answer uses real grading and is recorded only on submission', async ({ user, data, vocabulary }) => {
  await data.prepareUser({ plan: 'pro' })
  await selectQuestions(user, 'definition_to_word', 'single_word')
  const deck = await data.create({ name: 'Typed financial expression', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  await user.page.getByRole('textbox', { name: 'Your word', exact: true }).fill('bank')
  const graded = user.page.waitForResponse(response => response.url().endsWith('/study:grade') && response.request().method() === 'POST')
  await user.page.getByRole('button', { name: /^Check answer/ }).click()
  expect((await graded).status()).toBe(200)
  await expect(user.page.getByText('That fits.', { exact: true })).toBeVisible()
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  await finishStudy(user.page)
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
})

test('a typed definition uses dynamic sense choices and semantic feedback from the decision boundary', async ({ user, data, vocabulary, scenarios }) => {
  await data.prepareUser({ plan: 'pro' })
  await selectQuestions(user, 'word_to_definition', 'short_answer')
  const deck = await data.create({ name: 'Typed financial meaning', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  const answer = `An institution where people keep savings and borrow money, financial services for ${user.subject}.`
  await scenarios.register({ id: randomUUID(), path: '/decisions', contains: user.subject, responses: [
    { status: 200, body: { answers: { defined_meaning: { type: 'choice', choice: `sense_${vocabulary.bankFinancial.sense_id}` } } } },
    { status: 200, body: { answers: { accuracy: { type: 'choice', choice: 'accurate' }, coverage: { type: 'choice', choice: 'sufficient' } } } },
  ] })
  await startStudy(user.page, deck.id)
  await user.page.getByRole('textbox', { name: 'Your answer', exact: true }).fill(answer)
  await user.page.getByRole('button', { name: /^Check answer/ }).click()
  await expect(user.page.getByText('That fits.', { exact: true })).toBeVisible()
  await finishStudy(user.page)
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
})
