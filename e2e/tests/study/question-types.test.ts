import { randomUUID } from 'node:crypto'
import { test, expect } from '../../fixtures/index.ts'
import { answerChoice, finishStudy, selectQuestions, startStudy } from '../../support/study.ts'

const choices = [
  ['definition_to_word', 'bank'],
  ['word_to_definition', 'an institution where people keep and borrow money'],
  ['cloze_to_word', 'bank'],
  ['context_to_word', 'bank'],
  ['meaning_in_context', 'an institution where people keep and borrow money'],
  ['word_to_usage', 'She deposited her savings at the bank.'],
  ['dialogue_completion', 'You can deposit them at the bank.'],
  ['sentence_rewrite', 'She deposited her savings at the bank.'],
] as const

for (const [kind, answer] of choices) {
  test(`${kind} presents an actionable question and submits the authored correct answer`, async ({ user, data, vocabulary }) => {
    await selectQuestions(user, kind)
    const deck = await data.create({ name: `Exercise ${kind}`, type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
    await startStudy(user.page, deck.id)
    await answerChoice(user.page, answer)
    await finishStudy(user.page)
    expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
  })
}

test("don't know shows feedback and repeats the question in the next round", async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Retry finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, deck.id)
  await user.page.getByRole('button', { name: "I don’t know", exact: true }).click()
  await expect(user.page.getByText('Try this again next round.', { exact: true })).toBeVisible()
  await user.page.getByRole('button', { name: /^Continue/ }).click()
  await expect(user.page.getByRole('heading', { name: 'Ready for another pass.' })).toBeVisible()
  await user.page.getByRole('button', { name: 'Continue to round 2', exact: true }).click()
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
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

for (const [kind, answer, label] of [
  ['word_to_usage', 'She deposited her savings at the bank.', 'Your answer'],
  ['sentence_rewrite', 'She deposited her savings at the bank.', 'Your rewrite'],
] as const) {
  test(`${kind} accepts a typed response and renders semantic feedback before saving`, async ({ user, data, vocabulary, scenarios }) => {
    await data.prepareUser({ plan: 'pro' })
    await selectQuestions(user, kind, 'short_answer')
    const deck = await data.create({ name: `Typed ${kind}`, type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
    const response = `${answer} This was recommended by ${user.subject}.`
    const assessment = { meaning: { type: 'choice', choice: 'correct' }, form: { type: 'choice', choice: 'correct' }, construction: { type: 'noul', noul: 1 }, collocation: { type: 'noul', noul: 1 }, appropriacy: { type: 'noul', noul: 1 }, ...(kind === 'sentence_rewrite' ? { meaning_preservation: { type: 'choice', choice: 'preserved' } } : {}) }
    await scenarios.register({ id: randomUUID(), path: '/decisions', contains: user.subject, responses: [
      { status: 200, body: { answers: { used: { type: 'noul', noul: 1 } } } },
      { status: 200, body: { answers: assessment } },
    ] })
    await startStudy(user.page, deck.id)
    await user.page.getByRole('textbox', { name: label, exact: true }).fill(response)
    await user.page.getByRole('button', { name: /^Check answer/ }).click()
    await expect(user.page.getByText('That fits.', { exact: true })).toBeVisible()
    expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
    await finishStudy(user.page)
    expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
  })
}

for (const kind of ['context_to_word', 'cloze_to_word']) {
  test(`${kind} accepts a typed lexical answer and preserves its draft on reload`, async ({ user, data, vocabulary }) => {
    await data.prepareUser({ plan: 'pro' })
    await selectQuestions(user, kind, 'single_word')
    const deck = await data.create({ name: `Typed ${kind}`, type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
    await startStudy(user.page, deck.id)
    const input = user.page.getByRole('textbox', { name: 'Your word', exact: true })
    await input.fill('bank')
    await user.page.reload()
    await expect(input).toHaveValue('bank')
    await user.page.getByRole('button', { name: /^Check answer/ }).click()
    await expect(user.page.getByText('That fits.', { exact: true })).toBeVisible()
    await finishStudy(user.page)
    expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
  })
}
