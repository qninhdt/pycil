import { expect,test } from './fixtures'
import { api } from './helpers/api'

import type { StudySummary } from '../../src/lib/home-api'

import { randomUUID } from 'node:crypto'

test('copy persists independent memberships; reference cycles terminate with deduplicated progress', async ({ page, profile, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const deck = await nodes.create({ type: 'DECK', parent_id: folder.id, sense_ids: [1, 2] })
  expect((await api(page, 'nodes', 'POST', { type: 'REFERENCE', name: 'invalid ancestor', parent_id: folder.id, reference_id: folder.id })).status).toBe(422)
  const sibling = await nodes.create({ type: 'FOLDER' })
  const reference = await api<{ id: string }>(page, 'nodes', 'POST', { type: 'REFERENCE', name: 'loop', parent_id: folder.id, reference_id: sibling.id })
  expect(reference.status).toBe(201); nodes.track(reference.body.id)
  const backReference = await api<{ id: string }>(page, 'nodes', 'POST', { type: 'REFERENCE', name: 'return loop', parent_id: sibling.id, reference_id: folder.id })
  expect(backReference.status).toBe(201); nodes.track(backReference.body.id)
  expect((await api<StudySummary>(page, `study/progress?node_id=${folder.id}`)).body.total).toBe(2)
  const copy = await api<{ id: string }>(page, `nodes/${folder.id}:copy`, 'POST', { parent_id: profile.personal_node_id })
  expect(copy.status).toBe(201); nodes.track(copy.body.id)
  const children = (await api<{ nodes: { id: string; type: string }[] }>(page, `nodes?parent_id=${copy.body.id}`)).body.nodes
  const copiedDeck = children.find(node => node.type === 'DECK')!
  expect(copiedDeck.id).not.toBe(deck.id)
  expect((await api(page, `nodes/${copiedDeck.id}:modifySenses`, 'POST', { add: [3], remove: [1] })).status).toBe(200)
  expect((await api<{ senses: { sense_id: number }[] }>(page, `nodes/${deck.id}/senses?limit=100`)).body.senses.map(sense => sense.sense_id).sort()).toEqual([1, 2])
  expect((await api<{ senses: { sense_id: number }[] }>(page, `nodes/${copiedDeck.id}/senses?limit=100`)).body.senses.map(sense => sense.sense_id).sort()).toEqual([2, 3])
  await page.goto(`/app/personal/${copy.body.id}/words`)
  await expect(page.getByRole('button', { name: /^View / })).toHaveCount(3)
})

test('all paginated source decks resolve canonically without duplicates', async ({ page, nodes }) => {
  const root = await nodes.create({ type: 'FOLDER' })
  for (let group = 0; group < 2; group++) {
    const folder = await nodes.create({ type: 'FOLDER', parent_id: root.id })
    for (let n = 0; n < 11; n++) await nodes.create({ type: 'DECK', parent_id: folder.id, name: `source-${group}-${n}`, sense_ids: [1] })
  }
  await page.goto(`/app/personal/${root.id}/words`)
  await page.getByRole('button', { name: /^View bank:/ }).click()
  await page.getByRole('button', { name: 'Load more source decks', exact: true }).click()
  await expect(page.getByRole('dialog').getByRole('link', { name: /^source-/ })).toHaveCount(20)
  await page.getByRole('button', { name: 'Load more source decks', exact: true }).click()
  const links = page.getByRole('dialog').getByRole('link', { name: /^source-/ })
  await expect(links).toHaveCount(22)
  const hrefs = await links.evaluateAll(links => links.map(link => link.getAttribute('href')))
  expect(new Set(hrefs).size).toBe(22)
  expect(hrefs.every(href => href?.startsWith('/app/personal/'))).toBe(true)
})

test('Create reference UI persists a live link, follows source changes and keeps memberships deduplicated', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [1] })
  await page.goto(`/app/personal/${deck.id}`)
  await page.getByRole('button', { name: `Settings for ${deck.name}` }).click()
  await page.getByRole('menuitem', { name: 'Create reference', exact: true }).click()
  const form = page.getByRole('dialog', { name: 'Create reference', exact: true })
  const name = 'linked-' + randomUUID()
  await form.getByRole('textbox', { name: 'Title', exact: true }).fill(name)
  const saved = page.waitForResponse(response => response.url().endsWith('/nodes') && response.request().method() === 'POST')
  await form.getByRole('button', { name: 'Create reference', exact: true }).click()
  const reference = await (await saved).json(); nodes.track(reference.id)
  expect(reference.reference_id).toBe(deck.id)
  await page.goto(`/app/personal/${reference.id}/words`)
  await expect(page.getByRole('button', { name: /^View / })).toHaveCount(1)
  expect((await api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [2], remove: [] })).status).toBe(200)
  await page.reload()
  await expect(page.getByRole('button', { name: /^View / })).toHaveCount(2)
  expect((await api<StudySummary>(page, `study/progress?node_id=${reference.id}`)).body.total).toBe(2)
  expect((await api<{ parent_id: string }>(page, `nodes/${reference.id}`)).body.parent_id).toBe(profile.personal_node_id)
})
