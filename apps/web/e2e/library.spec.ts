import { randomUUID } from 'node:crypto'
import { test, expect, api } from './fixtures'
import type { StudySummary } from '../src/lib/home-api'

test('folder and meaning pagination, search, sorting, state filters and breadcrumbs use real scopes', async ({ page, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const decks = []
  for (let n = 0; n < 13; n++) decks.push(await nodes.create({ type: 'DECK', parent_id: folder.id, name: `native-${n.toString().padStart(2, '0')}`, sense_ids: [100 + n, 1] }))
  await page.goto(`/app/personal/${folder.id}/words`)
  await expect(page.getByRole('heading', { name: folder.name, exact: true })).toBeVisible()
  const first = await api<{ nodes: { id: string }[]; next_cursor: string }>(page, `nodes?parent_id=${folder.id}&limit=12`)
  expect(first.body.nodes).toHaveLength(12)
  const second = await api<{ nodes: { id: string }[] }>(page, `nodes?parent_id=${folder.id}&limit=12&cursor=${encodeURIComponent(first.body.next_cursor)}`)
  expect(second.body.nodes).toHaveLength(1)
  expect(new Set([...first.body.nodes, ...second.body.nodes].map(n => n.id)).size).toBe(13)
  await nodes.create({ type: 'DECK', name: 'native-00', sense_ids: [1] })
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

test('atomic sense deltas preserve concurrent additions; invalid batches and system/cycle writes change nothing', async ({ page, profile, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const child = await nodes.create({ type: 'FOLDER', parent_id: folder.id })
  const deck = await nodes.create({ type: 'DECK', sense_ids: [1] })
  const writes = await Promise.all([2, 3].map(id => api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [id], remove: [] })))
  expect(writes.map(write => write.status)).toEqual([200, 200])
  const editor = async () => (await api<{ sense_ids: number[] }>(page, `nodes/${deck.id}/editor`)).body.sense_ids
  expect((await editor()).sort()).toEqual([1, 2, 3])
  expect((await api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [4, 2147483647], remove: [1] })).status).toBe(422)
  expect((await editor()).sort()).toEqual([1, 2, 3])
  expect((await api(page, `nodes/${folder.id}:move`, 'POST', { parent_id: child.id })).status).toBe(422)
  expect((await api(page, `nodes/${profile.personal_node_id}`, 'DELETE')).status).toBe(422)
  expect((await api(page, `nodes/${profile.personal_node_id}`, 'PATCH', { name: 'must stay Personal' })).status).toBe(422)
  expect((await api(page, `nodes/${deck.id}:move`, 'POST', { parent_id: deck.id })).status).toBeGreaterThanOrEqual(400)
  const races = await Promise.all([api(page, `nodes/${folder.id}:move`, 'POST', { parent_id: child.id }), api(page, `nodes/${child.id}:move`, 'POST', { parent_id: profile.personal_node_id })])
  expect(races.every(r => [200, 422].includes(r.status))).toBe(true)
  await page.goto(`/app/personal/${deck.id}/words`)
  await expect(page.getByRole('button', { name: /^View / })).toHaveCount(3)
})

test('delete cancellation preserves a subtree and confirmed deletion removes descendants and restores navigation', async ({ page, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const deck = await nodes.create({ type: 'DECK', parent_id: folder.id, sense_ids: [1] })
  await page.goto(`/app/personal/${folder.id}`)
  await page.getByRole('button', { name: `Settings for ${folder.name}`, exact: true }).click()
  await page.getByRole('menuitem', { name: 'Delete', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Cancel', exact: true }).click()
  expect((await api(page, `nodes/${deck.id}`)).status).toBe(200)
  await page.getByRole('button', { name: `Settings for ${folder.name}`, exact: true }).click()
  await page.getByRole('menuitem', { name: 'Delete', exact: true }).click()
  await page.getByRole('alertdialog').getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Personal', exact: true })).toBeVisible()
  expect((await api(page, `nodes/${deck.id}`)).status).toBe(404)
  expect((await api(page, `nodes/${folder.id}`)).status).toBe(404)
})

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
  expect((await api<{ sense_ids: number[] }>(page, `nodes/${deck.id}/editor`)).body.sense_ids.sort()).toEqual([1, 2])
  expect((await api<{ sense_ids: number[] }>(page, `nodes/${copiedDeck.id}/editor`)).body.sense_ids.sort()).toEqual([2, 3])
  await page.goto(`/app/personal/${copy.body.id}/words`)
  await expect(page.getByRole('button', { name: /^View / })).toHaveCount(3)
})

test('Discovery filters and pages public records; guessed private IDs and editor routes remain hidden', async ({ page, profile, nodes }) => {
  const marker = 'public ' + randomUUID()
  for (let n = 0; n < 13; n++) {
    const deck = await nodes.create({ type: 'DECK', name: `${marker} ${n}` })
    expect((await api(page, `nodes/${deck.id}:move`, 'POST', { parent_id: profile.published_node_id, confirm_publication: true })).status).toBe(200)
    expect((await api(page, `nodes/${deck.id}/editor`, 'GET', undefined, false)).status).toBe(401)
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

test('flashcards traverse native pagination, keep account-scoped position and never submit reviews', async ({ page, profile, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: Array.from({ length: 101 }, (_, n) => n + 100) })
  const before = (await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body
  const writes: string[] = []
  page.on('request', request => { if (request.url().includes('/study:grade') || request.url().includes('/study:submitReviews')) writes.push(request.url()) })
  await page.goto(`/focus/flashcards?node=${deck.id}`)
  await expect(page.getByText('1 / 101', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Previous flashcard' })).toBeDisabled()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByText('2 / 101', { exact: true })).toBeVisible()
  await page.locator('main').click({ position: { x: 5, y: 80 } })
  await page.keyboard.press('Space')
  await expect(page.getByRole('button', { name: /^Flip back to word/ })).toBeVisible()
  await page.reload()
  await expect(page.getByText('2 / 101', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Flip back to word/ })).toBeVisible()
  expect(await page.evaluate(({ id, node }) => JSON.parse(localStorage.getItem(`pycil:flashcards:${id}:${node}`)!), { id: profile.id, node: deck.id })).toEqual({ index: 1, revealed: true })
  const after = (await api<StudySummary>(page, `study/progress?node_id=${deck.id}`)).body
  expect(after).toEqual({ ...before, as_of: expect.any(String) })
  expect(writes).toEqual([])
  const empty = await nodes.create({ type: 'DECK' })
  await page.goto(`/focus/flashcards?node=${empty.id}`)
  await expect(page.getByRole('heading', { name: 'No flashcards here yet.' })).toBeVisible()
})

test('native folder and deck quotas reject atomically, including concurrent creates at the boundary', async ({ page, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  for (let n = 0; n < 15; n++) await nodes.create({ type: 'DECK', parent_id: folder.id })
  const results = await Promise.all([0, 1].map(n => api<{ id: string; error?: string }>(page, 'nodes', 'POST', { type: 'DECK', name: `quota-${n}`, parent_id: folder.id, sense_ids: [] })))
  expect(results.map(result => result.status).sort()).toEqual([201, 422])
  for (const result of results) { if (result.status === 201) nodes.track(result.body.id); else expect(result.body.error).toBe('quota_exceeded') }
  const deck = await nodes.create({ type: 'DECK', sense_ids: [1] })
  const tooMany = [...Array.from({ length: 32 }, (_, n) => n + 1), ...Array.from({ length: 89 }, (_, n) => n + 100)]
  const denied = await api<{ error: string }>(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: tooMany, remove: [] })
  expect(denied).toMatchObject({ status: 422, body: { error: 'deck_sense_limit_exceeded' } })
  expect((await api<{ sense_ids: number[] }>(page, `nodes/${deck.id}/editor`)).body.sense_ids).toEqual([1])
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

test('Library latest search wins over delayed native reads and tab Back/Forward retains canonical routes', async ({ page, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [1, 100] })
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
  await page.route(`**/api/v1/nodes/${deck.id}/senses*`, async route => {
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

test('double submission and an accepted creation with lost response produce one native deck', async ({ page, profile, nodes }) => {
  const name = 'uncertain-' + randomUUID()
  let creates = 0
  page.on('request', request => { if (request.url().endsWith('/api/v1/nodes') && request.method() === 'POST') creates++ })
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/v1/nodes', async route => {
    if (route.request().method() !== 'POST') { await route.continue(); return }
    const response = await route.fetch()
    expect(response.status()).toBe(201)
    nodes.track((await response.json()).id)
    await gate
    await route.abort('connectionfailed')
  }, { times: 1 })
  await page.goto('/app/personal?create=deck')
  const form = page.getByRole('dialog', { name: 'New deck' })
  await form.getByRole('textbox', { name: 'Title' }).fill(name)
  await form.getByRole('button', { name: 'Create deck', exact: true }).evaluate(button => { (button as HTMLButtonElement).click(); (button as HTMLButtonElement).click() })
  await expect(form.getByRole('button', { name: 'Saving…', exact: true })).toBeDisabled()
  release()
  await expect(form.getByRole('alert')).toBeVisible()
  await expect(form.getByRole('textbox', { name: 'Title' })).toHaveValue(name)
  expect(creates).toBe(1)
  const persisted = (await api<{ nodes: { id: string }[] }>(page, `nodes/${profile.personal_node_id}:search?q=${name}`)).body.nodes
  expect(persisted).toHaveLength(1)
  await page.reload()
  expect((await api<{ nodes: unknown[] }>(page, `nodes/${profile.personal_node_id}:search?q=${name}`)).body.nodes).toHaveLength(1)
})

test('global owned-node quota serializes concurrent writes and deletion restores one slot', async ({ page, nodes }) => {
  test.setTimeout(120000)
  const created: { id: string }[] = []
  let parent = ''
  for (let group = 0; group < 5; group++) {
    const folder = await nodes.create({ type: 'FOLDER' }); created.push(folder); parent = folder.id
    for (let n = 0; n < 15 && created.length < 77; n++) created.push(await nodes.create({ type: 'DECK', parent_id: parent }))
  }
  expect(created).toHaveLength(77)
  const writes = await Promise.all([0, 1].map(n => api<{ id: string; error?: string }>(page, 'nodes', 'POST', { type: 'DECK', name: `owned-quota-${n}`, parent_id: parent, sense_ids: [] })))
  expect(writes.map(result => result.status).sort()).toEqual([201, 422])
  for (const write of writes) { if (write.status === 201) nodes.track(write.body.id); else expect(write.body.error).toBe('quota_exceeded') }
  expect((await api(page, `nodes/${created[0].id}:copy`, 'POST', { parent_id: parent })).status).toBe(422)
  expect((await api(page, `nodes/${created.at(-1)!.id}`, 'DELETE')).status).toBe(204)
  const replacement = await nodes.create({ type: 'DECK', parent_id: parent })
  expect(replacement.id).not.toBe(created.at(-1)!.id)
})
