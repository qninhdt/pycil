import { test, expect } from '../../fixtures/index.ts'
import { answerChoice, finishStudy, selectQuestions, startStudy } from '../../support/study.ts'

test('only submission records learning, shared senses have the same progress in another deck', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const sense = vocabulary.bankFinancial.sense_id
  const deck = await data.create({ name: 'Everyday finances', type: 'deck', sense_ids: [sense] })
  const other = await data.create({ name: 'Shared finance meaning', type: 'deck', sense_ids: [sense] })
  await startStudy(user.page, deck.id)
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ new: 1, studied: 0 })
  await answerChoice(user.page, 'bank')
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ new: 1, studied: 0 })
  await finishStudy(user.page)
  for (const node of [deck, other]) expect(await user.api.call(`study/progress?node_id=${node.id}`)).toMatchObject({ new: 0, studied: 1, total: 1 })
  expect(await user.api.call('study/progress')).toMatchObject({ total: 1, studied: 1 })
})

test('review selects due meanings and practice accepts a meaning that is not yet due', async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  const deck = await data.create({ name: 'Due finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await data.prepareUser({ dueSense: vocabulary.bankFinancial.sense_id })
  await startStudy(user.page, deck.id, 'due')
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ due: 0, not_due: 1 })
  await user.page.getByRole('link', { name: 'Back to My Library', exact: true }).click()
  await expect(user.page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
  await startStudy(user.page, deck.id, 'auto')
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
  expect(await user.api.call('study/activity')).toMatchObject({ applied_events: 2, practice_events: 0 })
})
