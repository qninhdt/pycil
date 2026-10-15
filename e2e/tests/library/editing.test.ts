import { test, expect } from '../../fixtures/index.ts'
import type { Node } from '../../support/api.ts'

test('create a deck through the UI and read persisted content after reload', async ({ user, data }) => {
  const { page, api } = user
  const title = `Travel ${user.subject.slice(-8)}`
  await page.goto('/app/personal?create=deck')
  const dialog = page.getByRole('dialog', { name: 'New deck', exact: true })
  await dialog.getByLabel('Title', { exact: true }).fill(title)
  await dialog.getByLabel('Description (optional)').fill('Expressions for the next journey')
  const saved = page.waitForResponse(response => response.url().endsWith('/v1/nodes') && response.request().method() === 'POST')
  await dialog.getByRole('button', { name: 'Create deck', exact: true }).click()
  const response = await saved
  expect(response.status()).toBe(201)
  const deck = await response.json() as Node
  data.track(deck.id)
    await expect(page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
    await expect(page.getByRole('heading', { level: 1 })).toContainText(title)
    await page.reload()
    await expect(page.getByRole('heading', { level: 1 })).toContainText(title)
    expect(await api.call<Node>(`nodes/${deck.id}`)).toMatchObject({ name: title, type: 'deck', owner_id: user.account.id })
})

test('edit details, copy and remove a meaning without changing the copy, then delete the original', async ({ user, data, vocabulary }) => {
  const source = await data.create({ name: 'Original finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  const folder = await data.create({ name: 'Independent copies', type: 'folder' })
  await user.page.goto(`/app/personal/${source.id}`)
  await user.page.getByRole('button', { name: `Settings for ${source.name}` }).click()
  await user.page.getByRole('menuitem', { name: 'Edit details', exact: true }).click()
  const edit = user.page.getByRole('dialog')
  await edit.getByLabel('Title', { exact: true }).fill('Updated finance')
  await edit.getByLabel('Description (optional)').fill('Owned financial vocabulary')
  await edit.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(user.page.getByRole('heading', { level: 1 })).toContainText('Updated finance')
  await user.page.getByRole('button', { name: 'Settings for Updated finance', exact: true }).click()
  await user.page.getByRole('menuitem', { name: 'Copy', exact: true }).click()
  const destination = user.page.getByRole('dialog', { name: 'Choose a destination', exact: true })
  await destination.getByRole('button', { name: folder.name, exact: true }).click()
  const copied = user.page.waitForResponse(response => response.url().endsWith(`/nodes/${source.id}:copy`) && response.request().method() === 'POST')
  await destination.getByRole('button', { name: 'Copy here', exact: true }).click()
  const copyResponse = await copied
  expect(copyResponse.status()).toBe(201)
  const copy = await copyResponse.json() as { id: string }
  data.track(copy.id)
  await user.page.getByRole('tab', { name: 'Words', exact: true }).click()
  await user.page.getByRole('button', { name: /View bank.*institution/ }).click()
  await user.page.getByRole('dialog').getByRole('button', { name: 'Remove from deck', exact: true }).click()
  expect(await user.api.call(`study/progress?node_id=${source.id}`)).toMatchObject({ total: 0 })
  expect(await user.api.call(`study/progress?node_id=${copy.id}`)).toMatchObject({ total: 1 })
  await user.page.goto(`/app/personal/${source.id}`)
  await user.page.getByRole('button', { name: 'Settings for Updated finance', exact: true }).click()
  await user.page.getByRole('menuitem', { name: 'Delete', exact: true }).click()
  await user.page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click()
  expect(await user.api.call(`nodes/${source.id}`)).toMatchObject({ id: source.id })
  await user.page.getByRole('button', { name: 'Settings for Updated finance', exact: true }).click()
  await user.page.getByRole('menuitem', { name: 'Delete', exact: true }).click()
  await user.page.getByRole('alertdialog').getByRole('button', { name: 'Delete', exact: true }).click()
  await expect.poll(async () => { try { await user.api.call(`nodes/${source.id}`, 'GET', undefined, 404); return true } catch { return false } }).toBe(true)
  expect(await user.api.call(`study/progress?node_id=${copy.id}`)).toMatchObject({ total: 1 })
})

test('moving a deck changes its parent and keeps its original content', async ({ user, data, vocabulary }) => {
  const folder = await data.create({ name: 'Moved vocabulary', type: 'folder' })
  const deck = await data.create({ name: 'Move finance', type: 'deck', sense_ids: [vocabulary.bankFinancial.sense_id] })
  await user.page.goto(`/app/personal/${deck.id}`)
  await user.page.getByRole('button', { name: `Settings for ${deck.name}`, exact: true }).click()
  await user.page.getByRole('menuitem', { name: 'Move', exact: true }).click()
  const destination = user.page.getByRole('dialog', { name: 'Choose a destination', exact: true })
  await destination.getByRole('button', { name: folder.name, exact: true }).click()
  await destination.getByRole('button', { name: 'Move here', exact: true }).click()
  await expect(user.page.getByRole('navigation', { name: 'breadcrumb' })).toContainText(folder.name)
  expect(await user.api.call(`nodes/${deck.id}`)).toMatchObject({ parent_id: folder.id })
  expect(await user.api.call(`study/progress?node_id=${deck.id}`)).toMatchObject({ total: 1 })
  await expect(user.page).toHaveURL(new RegExp(`/app/personal/${folder.id}$`))
  await user.page.getByRole('link').filter({ hasText: deck.name }).click()
  await expect(user.page).toHaveURL(new RegExp(`/app/personal/${deck.id}$`))
  await user.page.reload()
  await expect(user.page.getByRole('heading', { level: 1 })).toContainText(deck.name)
})

test('double clicking create sends one write and a lost accepted response preserves the draft', async ({ user, data }) => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  let creates = 0
  user.page.on('request', request => { if (request.url().endsWith('/v1/nodes') && request.method() === 'POST') creates++ })
  await user.page.route('**/v1/nodes', async route => {
    if (route.request().method() !== 'POST') return route.continue()
    const response = await route.fetch()
    expect(response.status()).toBe(201)
    data.track((await response.json() as { id: string }).id)
    await gate
    await route.abort('connectionreset')
  }, { times: 1 })
  const name = 'An uncertain accepted creation'
  try {
    await user.page.goto('/app/personal?create=deck')
    const dialog = user.page.getByRole('dialog', { name: 'New deck', exact: true })
    await dialog.getByLabel('Title', { exact: true }).fill(name)
    await dialog.getByRole('button', { name: 'Create deck', exact: true }).dblclick()
    await expect(dialog.getByRole('button', { name: 'Saving…', exact: true })).toBeDisabled()
    release()
    await expect(dialog.getByRole('alert')).toBeVisible()
    await expect(dialog.getByLabel('Title', { exact: true })).toHaveValue(name)
    expect(creates).toBe(1)
    expect(await user.api.call(`nodes/${user.account.personal_node_id}:search?q=${encodeURIComponent(name)}`)).toMatchObject({ nodes: [expect.objectContaining({ name })] })
    await user.page.goto('/app/personal')
    await expect(user.page.getByRole('heading', { name, exact: true })).toBeVisible()
  } finally { release() }
})
