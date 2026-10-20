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
  for (const node of [deck, other]) expect(await user.api.call(`study/progress?node_id=${node.id}`)).toMatchObject({ new: 0, studied: 1, total: 1, not_due: 1, due: 0 })
  expect(await user.api.call('study/progress')).toMatchObject({ total: 1, studied: 1, not_due: 1, due: 0 })
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

for (const selection of ['new', 'auto'] as const) test(`finishing ${selection === 'new' ? 'learning' : 'practice'} from the Library root returns Home`, async ({ user, data, vocabulary }) => {
  await selectQuestions(user)
  await data.create({ name: 'Root study vocabulary', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await startStudy(user.page, user.account.library_node_id, selection)
  await answerChoice(user.page, 'bank')
  await finishStudy(user.page)
  await user.page.getByRole('link', { name: 'Back to My Library', exact: true }).click()
  await expect(user.page).toHaveURL(/\/app$/)
  await expect(user.page.getByRole('main')).not.toContainText('This page could not be opened')
})
