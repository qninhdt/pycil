import { test, expect } from '../../fixtures/index.ts'
import { answerChoice, finishStudy, selectQuestions, startStudy } from '../../support/study.ts'

test('only submission records learning, shared senses have the same progress in another deck', async ({ actor, data, vocabulary }) => {
  await selectQuestions(actor)
  const sense = vocabulary.bankFinancial.sense_id
  const deck = await data.create({ name: 'Everyday finances', type: 'deck', sense_ids: [sense] })
  const other = await data.create({ name: 'Shared finance meaning', type: 'deck', sense_ids: [sense] })
  await startStudy(actor.page, deck.id)
  expect(await actor.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ new: 1, studied: 0 })
  await answerChoice(actor.page, 'bank')
  expect(await actor.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ new: 1, studied: 0 })
  await finishStudy(actor.page)
  for (const node of [deck, other]) expect(await actor.api.call(`study/progress?node_id=${node.id}`)).toMatchObject({ new: 0, studied: 1, total: 1 })
  expect(await actor.api.call('study/progress')).toMatchObject({ total: 1, studied: 1 })
})

test('review selects due meanings and practice accepts a meaning that is not yet due', async ({ actor, data, vocabulary }) => {
  await selectQuestions(actor)
  const deck = await data.create({ name: 'Due finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await data.prepareActor({ dueSense: vocabulary.bankFinancial.sense_id })
  await startStudy(actor.page, deck.id, 'due')
  await answerChoice(actor.page, 'bank')
  await finishStudy(actor.page)
  expect(await actor.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ due: 0, not_due: 1 })
  await actor.page.getByRole('link', { name: 'Back to My Library', exact: true }).click()
  await expect(actor.page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
  await startStudy(actor.page, deck.id, 'auto')
  await answerChoice(actor.page, 'bank')
  await finishStudy(actor.page)
  expect(await actor.api.call('study/activity')).toMatchObject({ applied_events: 2, practice_events: 0 })
})
