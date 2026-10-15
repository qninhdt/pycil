import { test, expect } from '../../fixtures/index.ts'
import { selectQuestions, answerChoice, finishStudy } from '../../support/study.ts'

test('a learner discovers published decks, guests read them and the learner saves a live reference and studies it', async ({ user, secondary, data, guest, vocabulary }) => {
  const name = `Public finance ${user.subject.slice(-8)}`
  const deck = await data.create({ name, type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await user.api.call(`nodes/${deck.id}:move`, 'POST', { parent_id: user.account.published_node_id, confirm_publication: true })
  await secondary.page.goto('/app/discovery')
  await secondary.page.getByRole('searchbox', { name: 'Search published material', exact: true }).fill(name)
  await secondary.page.getByRole('combobox', { name: 'Material type', exact: true }).selectOption('deck')
  const result = secondary.page.getByRole('link').filter({ hasText: name })
  await expect(result).toHaveAttribute('href', `/u/${user.account.id}/${deck.id}`)
  await result.click()
  await expect(secondary.page).toHaveURL(new RegExp(`/u/${user.account.id}/${deck.id}$`))
  await expect(secondary.page.getByRole('heading', { level: 1 })).toContainText(name)
  await guest.goto(`/u/${user.account.id}/${deck.id}`)
  await expect(guest.getByRole('heading', { level: 1 })).toContainText(name)
  await guest.getByRole('button', { name: `Settings for ${name}`, exact: true }).click()
  await expect(guest.getByRole('menuitem', { name: 'Copy link', exact: true })).toBeVisible()
  await expect(guest.getByRole('menuitem', { name: 'Edit details', exact: true })).not.toBeVisible()
  await expect(guest.getByRole('menuitem', { name: 'Delete', exact: true })).not.toBeVisible()
  await guest.keyboard.press('Escape')
  await expect(guest.getByRole('link', { name: 'Sign in to save or study', exact: true })).toBeVisible()
  await selectQuestions(secondary)
  await secondary.page.goto(`/u/${user.account.id}/${deck.id}`)
  await secondary.page.getByRole('button', { name: 'Save to Personal', exact: true }).click()
  const created = secondary.page.waitForResponse(response => response.url().endsWith('/v1/nodes') && response.request().method() === 'POST')
  await secondary.page.getByRole('dialog', { name: 'Choose a destination', exact: true }).getByRole('button', { name: 'Use this folder', exact: true }).click()
  const reference = await (await created).json() as { id: string }
  try {
    await secondary.page.goto(`/app/personal/${reference.id}`)
    await secondary.page.getByRole('link', { name: /^Learn new,/ }).click()
    await answerChoice(secondary.page, 'bank')
    await finishStudy(secondary.page)
    expect(await secondary.api.call(`study/progress?node_id=${reference.id}`)).toMatchObject({ studied: 1 })
    expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
  } finally { await secondary.api.call(`nodes/${reference.id}`, 'DELETE', undefined, [204, 404]) }
})

test('a learner studies a public deck directly without saving content into Personal', async ({ user, secondary, data, vocabulary }) => {
  const deck = await data.create({ name: 'Public direct study', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await user.api.call(`nodes/${deck.id}:move`, 'POST', { parent_id: user.account.published_node_id, confirm_publication: true })
  await selectQuestions(secondary)
  await secondary.page.goto(`/u/${user.account.id}/${deck.id}`)
  await secondary.page.getByRole('link', { name: /^Learn new/ }).click()
  await answerChoice(secondary.page, 'bank')
  await finishStudy(secondary.page)
  expect(await secondary.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 1 })
  expect(await secondary.api.call('study/progress')).toMatchObject({ total: 0 })
  expect(await secondary.api.call(`nodes?parent_id=${secondary.account.personal_node_id}`)).toMatchObject({ nodes: [] })
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ studied: 0 })
})

test('Discovery pages matching public decks and keeps private matches out of the results', async ({ user, secondary, data }) => {
  const marker = `Discovery ${user.subject.slice(-8)}`
  for (let index = 0; index < 13; index++) {
    const deck = await data.create({ name: `${marker} ${index + 1}`, type: 'deck' })
    await user.api.call(`nodes/${deck.id}:move`, 'POST', { parent_id: user.account.published_node_id, confirm_publication: true })
  }
  await data.create({ name: `${marker} private`, type: 'deck' })
  await secondary.page.goto('/app/discovery')
  await secondary.page.getByRole('searchbox', { name: 'Search published material', exact: true }).fill(marker)
  const cards = secondary.page.getByRole('list', { name: 'Published material', exact: true }).getByRole('listitem')
  await expect(cards).toHaveCount(12)
  const first = await cards.allTextContents()
  await secondary.page.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(cards).toHaveCount(1)
  expect(first).not.toContain(await cards.first().innerText())
  await expect(cards).not.toContainText('private')
  await secondary.page.getByRole('combobox', { name: 'Material type', exact: true }).selectOption('folder')
  await expect(secondary.page.getByText('No matching material.', { exact: true })).toBeVisible()
  await secondary.page.getByRole('combobox', { name: 'Material type', exact: true }).selectOption('deck')
  await expect(cards).toHaveCount(12)
  await expect(secondary.page.getByText('Page 1', { exact: true })).toBeVisible()
})
