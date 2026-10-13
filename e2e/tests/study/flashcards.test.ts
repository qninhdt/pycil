import { test, expect } from '../../fixtures/index.ts'

test('reveal, navigation and reload retain the position without writing learning progress', async ({ actor, data, vocabulary }) => {
  const deck = await data.create({ name: 'Reading finance and rivers', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id, vocabulary.bankRiver.sense_id] })
  const mutations: string[] = []
  actor.page.on('request', request => { if (request.method() === 'POST' && request.url().includes('/v1/study:')) mutations.push(request.url()) })
  await actor.page.goto(`/app/flashcards?node=${deck.id}`)
  await actor.page.getByRole('button', { name: 'Reveal meaning of bank', exact: true }).click()
  await expect(actor.page.locator('article[data-face="back"]')).toContainText('institution where people keep and borrow money')
  await actor.page.getByRole('button', { name: 'Next flashcard', exact: true }).click()
  await expect(actor.page.getByText('2 / 2', { exact: true })).toBeVisible()
  await actor.page.getByRole('button', { name: 'Reveal meaning of bank', exact: true }).click()
  await expect(actor.page.locator('article[data-face="back"]')).toContainText('ground along the side of a river')
  await actor.page.reload()
  await expect(actor.page.getByText('2 / 2', { exact: true })).toBeVisible()
  await expect(actor.page.locator('article[data-face="back"]')).toContainText('ground along the side of a river')
  expect(mutations).toEqual([])
  expect(await actor.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0, new: 2 })
})

test('an empty deck offers a route back to its library', async ({ actor, data }) => {
  const deck = await data.create({ name: 'Empty flashcards', type: 'deck' })
  await actor.page.goto(`/app/flashcards?node=${deck.id}`)
  await expect(actor.page.getByRole('heading', { name: 'No flashcards here yet.', exact: true })).toBeVisible()
  await actor.page.getByRole('link', { name: 'Back to Library', exact: true }).click()
  await expect(actor.page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
})

test('the 101st distinct meaning is reachable across the backend page boundary', async ({ actor, data, vocabulary }) => {
  const deck = await data.create({ name: 'Full flashcard pagination', type: 'deck', sense_ids: vocabulary.pagination.map(item => item.sense_id) })
  await actor.page.goto(`/app/flashcards?node=${deck.id}`)
  const next = actor.page.getByRole('button', { name: 'Next flashcard', exact: true })
  for (let position = 1; position <= 100; position++) {
    await expect(actor.page.getByText(`${position} / 101`, { exact: true })).toBeVisible()
    await next.click()
  }
  await expect(actor.page.getByText('101 / 101', { exact: true })).toBeVisible()
  await expect(next).toBeDisabled()
  await actor.page.getByRole('button', { name: /^Reveal meaning of/ }).click()
  const final = actor.page.locator('article[data-face="back"]')
  await expect.poll(async () => {
    const content = await final.innerText()
    return vocabulary.pagination.some(item => content.includes(item.definition))
  }).toBe(true)
  await actor.page.reload()
  await expect(actor.page.getByText('101 / 101', { exact: true })).toBeVisible()
  expect(await actor.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0, total: 101 })
})
