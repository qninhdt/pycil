import { test, expect } from '../../fixtures/index.ts'
import { finishStudy, selectQuestions, startStudy } from '../../support/study.ts'

test('a real decision provider grades a typed definition and submission records that feedback', async ({ actor, data, vocabulary }) => {
  await data.prepareActor({ plan: 'pro' })
  await selectQuestions(actor, 'word_to_definition', 'short_answer')
  const deck = await data.create({ name: 'Live definition grading', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(actor.page, deck.id)
  await actor.page.getByRole('textbox', { name: 'Your answer', exact: true }).fill('An institution where people deposit their savings and borrow money.')
  const graded = actor.page.waitForResponse(response => response.url().endsWith('/study:grade') && response.request().method() === 'POST', { timeout: 150_000 })
  await actor.page.getByRole('button', { name: /^Check answer/, exact: true }).click()
  const response = await graded
  expect(response.status()).toBe(200)
  const result = await response.json() as { diagnostics: { sense_id: number | null; accuracy: string; coverage: string } }
  expect(result.diagnostics).toMatchObject({ sense_id: vocabulary.bankFinancial.sense_id, accuracy: 'accurate', coverage: 'sufficient' })
  expect(await actor.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  await expect(actor.page.getByText('That fits.', { exact: true })).toBeVisible()
  await finishStudy(actor.page)
  expect(await actor.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
})
