import { randomUUID } from 'node:crypto'
import { api } from './helpers/api'
import { signIn } from './helpers/auth'

import { expect,test } from './fixtures'



import { publishedHref } from '../../src/lib/library-model'

test('atomic sense deltas preserve concurrent additions; invalid batches and system/cycle writes change nothing', async ({ page, profile, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const child = await nodes.create({ type: 'FOLDER', parent_id: folder.id })
  const deck = await nodes.create({ type: 'DECK', sense_ids: [1] })
  const writes = await Promise.all([2, 3].map(id => api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [id], remove: [] })))
  expect(writes.map(write => write.status)).toEqual([200, 200])
  const members = async () => (await api<{ senses: { sense_id: number }[] }>(page, `nodes/${deck.id}/senses?limit=100`)).body.senses.map(sense => sense.sense_id)
  expect((await members()).sort()).toEqual([1, 2, 3])
  expect((await api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [4, 2147483647], remove: [1] })).status).toBe(422)
  expect((await members()).sort()).toEqual([1, 2, 3])
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

test('create and rename a deck through UI without losing its placement', async ({ page, profile, nodes }) => {
  await page.goto('/app/personal?create=deck')
  const name = `e2e-${randomUUID()}`
  const form = page.getByRole('dialog', { name: 'New deck' })
  await form.getByRole('textbox', { name: 'Title' }).fill(name)
  const created = page.waitForResponse(response => response.url().endsWith('/api/v1/nodes') && response.request().method() === 'POST')
  await form.getByRole('button', { name: 'Create deck', exact: true }).click()
  const response = await created
  expect(response.status()).toBe(201)
  const deck = await response.json()
  nodes.track(deck.id)
  await expect(page.getByRole('heading', { name: name, exact: true })).toBeVisible()
  expect((await api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [1], remove: [] })).status).toBe(200)
  await page.getByRole('button', { name: `Settings for ${name}` }).click()
  await page.getByRole('menuitem', { name: 'Edit details' }).click()
  const edit = page.getByRole('dialog', { name: 'Edit deck' })
  await edit.getByRole('textbox', { name: 'Title' }).fill(`${name}-renamed`)
  await edit.getByRole('textbox', { name: 'Description' }).fill('Persisted <b>literal</b> description')
  const renamed = page.waitForResponse(response => response.url().endsWith(`/nodes/${deck.id}`) && response.request().method() === 'PATCH')
  await edit.getByRole('button', { name: 'Save changes' }).click()
  expect((await renamed).status()).toBe(200)
  await expect(edit).not.toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', { name: `${name}-renamed`, exact: true })).toBeVisible()
  const stored = await api<{ parent_id: string; description: string }>(page, `nodes/${deck.id}`)
  expect(stored.body.parent_id).toBe(profile.personal_node_id)
  const savedSenses = await api<{ senses: { sense_id: number }[] }>(page, `nodes/${deck.id}/senses`)
  expect(savedSenses.body.senses.map(sense => sense.sense_id)).toEqual([1])
  expect(stored.body.description).toBe('Persisted <b>literal</b> description')
  expect(await page.locator('b').filter({ hasText: 'literal' }).count()).toBe(0)
})

test('move and copy use real writes and preserve independent identities', async ({ page, profile, nodes }) => {
  const folder = await nodes.create({ type: 'FOLDER' })
  const deck = await nodes.create({ type: 'DECK' })
  await page.goto(`/app/personal/${deck.id}`)
  await page.getByRole('button', { name: `Settings for ${deck.name}` }).click()
  await page.getByRole('menuitem', { name: 'Move', exact: true }).click()
  const destination = page.getByRole('dialog', { name: 'Choose a destination' })
  await destination.getByRole('button', { name: folder.name, exact: true }).click()
  await destination.getByRole('button', { name: 'Move here', exact: true }).click()
  await expect(destination).not.toBeVisible()
  expect((await api<{ parent_id: string }>(page, `nodes/${deck.id}`)).body.parent_id).toBe(folder.id)
  await page.goto(`/app/personal/${deck.id}`)
  await page.getByRole('button', { name: `Settings for ${deck.name}` }).click()
  await page.getByRole('menuitem', { name: 'Copy', exact: true }).click()
  const copied = page.waitForResponse(response => response.url().endsWith(`/nodes/${deck.id}:copy`))
  await page.getByRole('dialog', { name: 'Choose a destination' }).getByRole('button', { name: 'Use this folder', exact: true }).click()
  const response = await copied
  expect(response.status()).toBe(201)
  const copy = await response.json()
  nodes.track(copy.id)
  expect(copy.id).not.toBe(deck.id)
  expect(copy.parent_id).toBe(profile.personal_node_id)
  expect((await api<{ parent_id: string }>(page, `nodes/${deck.id}`)).body.parent_id).toBe(folder.id)
})

test('another Clerk account cannot read or mutate a private deck', async ({ page, browser, baseURL, nodes, profile }) => {
  const deck = await nodes.create({ type: 'DECK' })
  const context = await browser.newContext({ baseURL })
  try {
    const other = await context.newPage()
    const second = await signIn(other, 'B')
    expect(second.id).not.toBe(profile.id)
    expect((await api(other, `nodes/${deck.id}`)).status).toBe(404)
    expect((await api(other, `nodes/${deck.id}`, 'PATCH', { name: 'unauthorized' })).status).toBe(404)
    expect((await api(other, `nodes/${deck.id}`, 'DELETE')).status).toBe(404)
    expect((await api<{ name: string }>(page, `nodes/${deck.id}`)).body.name).toBe(deck.name)
  } finally { await context.close() }
})

for (const revoke of ['unpublish', 'delete'] as const) test(`saved public references and flashcards become unavailable after ${revoke}`, async ({ page, browser, baseURL, nodes, profile }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [1] })
  const published = await api(page, `nodes/${deck.id}:move`, 'POST', { parent_id: profile.published_node_id, confirm_publication: true })
  expect(published.status).toBe(200)
  const context = await browser.newContext({ baseURL })
  let referenceId: string | undefined
  let other
  try {
    other = await context.newPage()
    const second = await signIn(other, 'B')
    expect(second.id).not.toBe(profile.id)
    await other.goto(publishedHref(profile.id, deck.id))
    await other.getByRole('button', { name: `Settings for ${deck.name}` }).click()
    await other.getByRole('menuitem', { name: 'Create reference', exact: true }).click()
    const created = other.waitForResponse(response => response.url().endsWith('/api/v1/nodes') && response.request().method() === 'POST')
    await other.getByRole('dialog', { name: 'Create reference', exact: true }).getByRole('button', { name: 'Create reference', exact: true }).click()
    const response = await created
    expect(response.status()).toBe(201)
    const reference = await response.json()
    referenceId = reference.id
    expect(reference.reference_id).toBe(deck.id)
    expect(reference.owner_id).toBe(second.id)
    expect(reference.parent_id).toBe(second.personal_node_id)
    await other.goto(`/app/personal/${referenceId}`)
    await expect(other.getByRole('heading', { name: deck.name, exact: true })).toBeVisible()
    await other.goto(`/focus/flashcards?node=${referenceId}`)
    await other.getByRole('button', { name: /^Reveal meaning of bank/ }).click()
    const revoked = revoke === 'delete' ? await api(page, `nodes/${deck.id}`, 'DELETE') : await api(page, `nodes/${deck.id}:move`, 'POST', { parent_id: profile.personal_node_id })
    expect(revoked.status).toBe(revoke === 'delete' ? 204 : 200)
    await other.reload()
    await expect(other.getByRole('button', { name: /^Flip back to word bank/ })).not.toBeVisible()
    await expect(other.getByRole('alert').filter({ hasText: /unavailable|not be found|no longer|could not/i })).toBeVisible()
    await other.goto(`/app/personal/${referenceId}`)
    await expect(other.getByText('Reference unavailable.', { exact: true })).toBeVisible()
    expect((await api(other, `nodes/${deck.id}`)).status).toBe(404)
    await other.getByRole('link', { name: 'Back to folder', exact: true }).click()
    await expect(other.getByRole('heading', { name: 'Personal', exact: true })).toBeVisible()
  } finally {
    try {
      if (other && referenceId) expect([204, 404]).toContain((await api(other, `nodes/${referenceId}`, 'DELETE')).status)
    } finally { await context.close() }
  }
})

test('failed deck edit retains saved metadata and a retry applies the draft atomically', async ({ page, nodes }) => {
  const deck = await nodes.create({ type: 'DECK', sense_ids: [1, 2] })
  await page.goto(`/app/personal/${deck.id}`)
  await page.getByRole('button', { name: `Settings for ${deck.name}` }).click()
  await page.getByRole('menuitem', { name: 'Edit details', exact: true }).click()
  const form = page.getByRole('dialog', { name: 'Edit deck', exact: true })
  await form.getByRole('textbox', { name: 'Title', exact: true }).fill('edited-' + randomUUID())
  const draft = await form.getByRole('textbox', { name: 'Title', exact: true }).inputValue()
  await page.route(`**/api/v1/nodes/${deck.id}`, route => route.request().method() === 'PATCH' ? route.abort('connectionfailed') : route.continue(), { times: 1 })
  await form.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(form.getByRole('alert')).toBeVisible()
  await expect(form.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue(draft)
  expect((await api<{ name: string }>(page, `nodes/${deck.id}`)).body.name).toBe(deck.name)
  await form.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(form).not.toBeVisible()
  expect((await api<{ name: string }>(page, `nodes/${deck.id}`)).body.name).toBe(draft)
  expect((await api<{ senses: unknown[] }>(page, `nodes/${deck.id}/senses`)).body.senses).toHaveLength(2)
})
