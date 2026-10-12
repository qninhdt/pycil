
import { randomUUID } from 'node:crypto'
import { parseLibrary } from '../../src/lib/home-api'
import { api } from './helpers/api'
import { signIn } from './helpers/auth'

import { expect,test } from './fixtures'

import { finish } from './helpers/study'

import { publishedHref } from '../../src/lib/library-model'

import type { StudySummary } from '../../src/lib/home-api'

test('Discovery filters and pages public records; guessed private IDs and mutation routes remain hidden', async ({ page, profile, nodes }) => {
  const marker = 'public ' + randomUUID()
  for (let n = 0; n < 13; n++) {
    const deck = await nodes.create({ type: 'DECK', name: `${marker} ${n}` })
    expect((await api(page, `nodes/${deck.id}:move`, 'POST', { parent_id: profile.published_node_id, confirm_publication: true })).status).toBe(200)
    expect((await api(page, `nodes/${deck.id}`, 'PATCH', { name: 'denied' }, false)).status).toBe(401)
  }
  const privateDeck = await nodes.create({ type: 'DECK', name: marker + ' secret' })
  await page.goto('/app/discovery')
  await page.getByRole('searchbox', { name: 'Search published material' }).fill(marker)
  const cards = page.getByRole('list', { name: 'Published material' }).getByRole('listitem')
  await expect(cards).toHaveCount(12)
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(cards).toHaveCount(1)
  await page.getByRole('combobox', { name: 'Material type' }).selectOption('FOLDER')
  await expect(page.getByText('No matching material.', { exact: true })).toBeVisible()
  await page.getByRole('combobox', { name: 'Material type' }).selectOption('DECK')
  await expect(page.getByText('Page 1', { exact: true })).toBeVisible()
  expect((await api(page, `nodes/${privateDeck.id}/senses`, 'GET', undefined, false)).status).toBe(404)
  expect((await api(page, `nodes/${privateDeck.id}`, 'GET', undefined, false)).status).toBe(404)
})

test('guests can read published decks and folders without exposing personal learning', async ({ page, profile, nodes, browser, baseURL }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const deck = await nodes.create({ type: 'DECK', parent_id: folder.id, sense_ids: [21] })
  expect((await api(page, `nodes/${folder.id}:move`, 'POST', { parent_id: profile.published_node_id, confirm_publication: true })).status).toBe(200)
  const context = await browser.newContext({ baseURL })
  try {
    const guest = await context.newPage()
    await guest.goto(`/u/${profile.id}`)
    await expect(guest.getByRole('region', { name: 'Folder contents', exact: true })).toContainText(folder.name)
    await guest.getByRole('link', { name: new RegExp(folder.name) }).click()
    await expect(guest.getByRole('heading', { name: folder.name })).toBeVisible()
    await guest.getByRole('link', { name: deck.name, exact: true }).click()
    await expect(guest.getByRole('heading', { name: deck.name })).toBeVisible()
    await expect(guest.getByRole('region', { name: 'Words', exact: true }).getByRole('link')).toHaveCount(1)
    await expect(guest.getByText('Due', { exact: true })).toHaveCount(0)
    await expect(guest.getByRole('link', { name: /^Learn new/ })).toHaveCount(0)
    expect((await api(guest, `nodes/${profile.personal_node_id}`, 'GET', undefined, false)).status).toBe(404)
  } finally { await context.close() }
})

test('public direct learning completes without saving foreign content into personal Library', async ({ page, profile, nodes, browser, baseURL }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [21] })
  expect((await api(page, `nodes/${deck.id}:move`, 'POST', { parent_id: profile.published_node_id, confirm_publication: true })).status).toBe(200)
  const context = await browser.newContext({ baseURL })
  try {
    const other = await context.newPage()
    const learner = await signIn(other, 'B')
    const before = (await api<StudySummary>(other, 'study/progress')).body
    await other.goto(publishedHref(profile.id, deck.id))
    await other.getByRole('link', { name: /^Learn new/ }).click()
    await expect(other.getByRole('button', { name: 'I don’t know', exact: true })).toBeVisible()
    await finish(other, learner.id)
    await expect(other.getByRole('heading', { name: 'Session complete', exact: true })).toBeVisible()
    expect((await api<StudySummary>(other, `study/progress?node_id=${deck.id}`)).body.studied).toBe(1)
    expect((await api<StudySummary>(other, 'study/progress')).body.total).toBe(before.total)
    await other.getByRole('button', { name: 'Exit learning mode' }).click()
    await expect(other).toHaveURL(new RegExp(`/app/u/${profile.id}/published/${deck.id}$`))
    expect((await api<{ nodes: { reference_id: string }[] }>(other, `nodes?parent_id=${learner.personal_node_id}`)).body.nodes.some(node => node.reference_id === deck.id)).toBe(false)
  } finally { await context.close() }
})

test('cancelled publication keeps a private subtree private and does not create retained references', async ({ page, profile, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const deck = await nodes.create({ type: 'DECK', parent_id: folder.id, sense_ids: [1] })
  const before = (await api<{ nodes: unknown[] }>(page, `nodes?parent_id=${profile.personal_node_id}`)).body.nodes.length
  await page.goto(`/app/personal/${folder.id}`)
  await page.getByRole('button', { name: `Settings for ${folder.name}` }).click()
  await page.getByRole('menuitem', { name: 'Publish', exact: true }).click()
  const popup = page.getByRole('alertdialog')
  await popup.getByRole('checkbox', { name: 'Keep a reference in Personal' }).check()
  await popup.getByRole('button', { name: 'Cancel', exact: true }).click()
  expect((await api(page, `nodes/${folder.id}`, 'GET', undefined, false)).status).toBe(404)
  expect((await api(page, `nodes/${deck.id}`, 'GET', undefined, false)).status).toBe(404)
  expect((await api<{ nodes: unknown[] }>(page, `nodes?parent_id=${profile.personal_node_id}`)).body.nodes).toHaveLength(before)
})

test('guest reads public routes and cannot access a private account', async ({ page }) => {
  await page.goto('/app/discovery')
  await expect(page.getByRole('heading', { name: 'Discovery' })).toBeVisible()
  const catalog = await api(page, 'discovery/nodes?limit=12', 'GET', undefined, false)
  expect(catalog.status).toBe(200)
  expect(() => parseLibrary(catalog.body)).not.toThrow()
  expect((await api(page, 'me', 'GET', undefined, false)).status).toBe(401)
  await page.goto('/app/dictionary')
  await expect(page.getByRole('searchbox', { name: 'Search word or expression' })).toBeVisible()
})

test('publication grants guest reads and unpublication revokes them', async ({ page, nodes }) => {
  const deck = await nodes.create({ type: 'DECK' })
  await page.goto(`/app/personal/${deck.id}`)
  expect((await api(page, `nodes/${deck.id}`, 'GET', undefined, false)).status).toBe(404)
  await page.getByRole('button', { name: `Settings for ${deck.name}` }).click()
  await page.getByRole('menuitem', { name: 'Publish', exact: true }).click()
  const confirm = page.getByRole('alertdialog')
  await confirm.getByRole('checkbox', { name: 'Keep a reference in Personal' }).check()
  const moved = page.waitForResponse(response => response.url().endsWith(`/nodes/${deck.id}:move`))
  await confirm.getByRole('button', { name: 'Publish', exact: true }).click()
  const response = await moved
  expect(response.status()).toBe(200)
  const result = await response.json()
  expect(typeof result.retained_reference_id).toBe('string')
  nodes.track(result.retained_reference_id)
  await expect(page).toHaveURL(new RegExp(`/published/${deck.id}$`))
  expect((await api(page, `nodes/${deck.id}`, 'GET', undefined, false)).status).toBe(200)
  await page.getByRole('button', { name: `Settings for ${deck.name}` }).click()
  await page.getByRole('menuitem', { name: 'Move to Personal', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Move to Personal', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/personal/${deck.id}$`))
  expect((await api(page, `nodes/${deck.id}`, 'GET', undefined, false)).status).toBe(404)
})
