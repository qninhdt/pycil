import { expect,test } from './fixtures'
import { api } from './helpers/api'

import type { StudySummary } from '../../src/lib/home-api'

test('folder and meaning pagination, search, sorting, state filters and breadcrumbs use real scopes', async ({ page, nodes }) => {
  const folder = await nodes.create({ type: 'folder' })
  const decks = []
  for (let n = 0; n < 13; n++) decks.push(await nodes.create({ type: 'deck', parent_id: folder.id, name: `native-${n.toString().padStart(2, '0')}`, sense_ids: [100 + n, 1] }))
  await page.goto(`/app/personal/${folder.id}/words`)
  await expect(page.getByRole('heading', { name: folder.name, exact: true })).toBeVisible()
  const first = await api<{ nodes: { id: string }[]; next_cursor: string }>(page, `nodes?parent_id=${folder.id}&limit=12`)
  expect(first.body.nodes).toHaveLength(12)
  const second = await api<{ nodes: { id: string }[] }>(page, `nodes?parent_id=${folder.id}&limit=12&cursor=${encodeURIComponent(first.body.next_cursor)}`)
  expect(second.body.nodes).toHaveLength(1)
  expect(new Set([...first.body.nodes, ...second.body.nodes].map(n => n.id)).size).toBe(13)
  await nodes.create({ type: 'deck', name: 'native-00', sense_ids: [1] })
  const scoped = await api<{ nodes: { id: string }[] }>(page, `nodes/${folder.id}:search?q=native-00`)
  expect(scoped.body.nodes.map(node => node.id)).toEqual([decks[0].id])
  expect((await api<StudySummary>(page, `study/progress?node_id=${folder.id}`)).body.total).toBe(14)
  const words = page.getByRole('region', { name: 'Words in this scope' })
  await expect(words.getByRole('button', { name: /^View / })).toHaveCount(12)
  const firstNames = await words.getByRole('button', { name: /^View / }).allTextContents()
  await words.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(words.getByRole('button', { name: /^View / })).toHaveCount(2)
  expect(await words.getByRole('button', { name: /^View / }).allTextContents()).not.toEqual(firstNames)
  await words.getByRole('searchbox', { name: 'Search words' }).fill('zzzmissing')
  await expect(words.getByText('No matching words.', { exact: true })).toBeVisible()
  await words.getByRole('button', { name: 'Clear filters', exact: true }).click()
  await expect(words.getByText('Page 1', { exact: true })).toBeVisible()
  await words.getByRole('radio', { name: /^Due, / }).click()
  await expect(words.getByText('No matching words.', { exact: true })).toBeVisible()
  await words.getByRole('radio', { name: /^All words,/ }).click()
  await words.getByRole('combobox', { name: 'Sort words' }).click()
  await page.getByRole('option', { name: 'Last reviewed', exact: true }).click()
  await expect(words.getByText('Page 1', { exact: true })).toBeVisible()
  await page.goto(`/app/personal/${decks[0].id}`)
  await expect(page.getByRole('link', { name: folder.name, exact: true }).first()).toBeVisible()
})

test('Library latest search wins over delayed native reads and tab Back/Forward retains canonical routes', async ({ page, nodes }) => {
  const deck = await nodes.create({ type: 'deck', sense_ids: [1, 100] })
  await page.goto(`/app/personal/${deck.id}/words`)
  await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('tab', { name: 'Overview', exact: true }).click()
  await expect(page).toHaveURL(new RegExp(`/personal/${deck.id}$`))
  await page.goBack()
  await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.goForward()
  await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('aria-selected', 'true')
  await page.getByRole('tab', { name: 'Words', exact: true }).click()
  let release!: () => void, reached!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const requested = new Promise<void>(resolve => { reached = resolve })
  await page.route(`**/v1/nodes/${deck.id}/senses*`, async route => {
    if (new URL(route.request().url()).searchParams.get('q') === 'bank') { reached(); await gate }
    await route.continue()
  })
  const search = page.getByRole('searchbox', { name: 'Search words', exact: true })
  await search.fill('bank'); await requested
  await search.fill('archive')
  await expect(page.getByRole('button', { name: /^View archive:/ })).toBeVisible()
  release()
  await expect(page.getByRole('button', { name: /^View bank:/ })).not.toBeVisible()
  await page.reload()
  await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('aria-selected', 'true')
})
