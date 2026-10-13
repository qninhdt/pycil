import { randomUUID } from 'node:crypto'
import { api } from './helpers/api'
import { signIn } from './helpers/auth'

import { expect,test } from './fixtures'

test('public dictionary data remains readable to guests while private context and workspace UI require sign-in', async ({ page }) => {
  await page.goto('/')
  expect((await api(page, 'words/1', 'GET', undefined, false)).status).toBe(200)
  expect((await api(page, 'me/words/1', 'GET', undefined, false)).status).toBe(401)
  await page.goto('/app/dictionary?q=bank')
  await expect(page.getByRole('heading', { name: 'Sign in to Pycil' })).toBeVisible()
  await signIn(page)
  await page.goto('/app/dictionary?q=bank')
  await page.getByRole('button', { name: 'bank Ready', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'bank', exact: true })).toBeVisible()
  await expect(page.getByText('I visited the bank.', { exact: true }).first()).toBeVisible()
  expect(await page.locator('t').count()).toBe(0)
  await page.getByRole('searchbox', { name: 'Search word or expression' }).fill('zzznoentry')
  await expect(page.getByText('No entries found. Try another spelling or expression.')).toBeVisible()
  await page.getByRole('button', { name: 'Clear search' }).click()
  await expect(page.getByText('Search for a word or expression to explore its meanings.')).toBeVisible()
})

test('a delayed older native Dictionary query cannot replace the latest search', async ({ page }) => {
  await signIn(page)
  let release!: () => void, reached!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const requested = new Promise<void>(resolve => { reached = resolve })
  await page.route('**/v1/words:search*', async route => {
    if (new URL(route.request().url()).searchParams.get('query') === 'bank') { reached(); await gate }
    await route.continue()
  })
  await page.goto('/app/dictionary')
  const search = page.getByRole('searchbox', { name: 'Search word or expression' })
  await search.fill('bank'); await requested
  await search.fill('archive')
  await expect(page.getByRole('button', { name: 'archive Ready', exact: true })).toBeVisible()
  release()
  await expect(page.getByRole('button', { name: 'bank Ready', exact: true })).not.toBeVisible()
  await page.getByRole('button', { name: 'archive Ready', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'archive', exact: true })).toBeVisible()
})

test('picker keeps selected meanings across searches, sends batched native reads and preserves concurrent membership', async ({ page, nodes }) => {
  const deck = await nodes.create({ type: 'deck', sense_ids: [32] })
  await page.goto(`/app/personal/${deck.id}/words`)
  await page.getByRole('button', { name: 'Add words', exact: true }).click()
  const picker = page.getByRole('dialog', { name: 'Add words to deck' })
  const batch = page.waitForResponse(response => response.url().endsWith('/words:batchPreview'))
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('bank')
  expect((await batch).status()).toBe(200)
  await picker.getByRole('checkbox').first().check()
  await picker.getByRole('searchbox', { name: 'Search words' }).fill('archive')
  await expect(picker.getByRole('checkbox').first()).toBeVisible()
  await picker.getByRole('checkbox').first().check()
  await expect(picker.getByText('2 meanings selected', { exact: true })).toBeVisible()
  expect((await api(page, `nodes/${deck.id}:modifySenses`, 'POST', { add: [31], remove: [] })).status).toBe(200)
  await picker.getByRole('button', { name: 'Add to deck', exact: true }).click()
  await expect(picker).not.toBeVisible()
  const membership = (await api<{ senses: { sense_id: number }[] }>(page, `nodes/${deck.id}/senses?limit=100`)).body
  expect(membership.senses.map(sense => sense.sense_id).sort((a, b) => a - b)).toEqual([1, 31, 32, 100])
  await page.reload()
  await expect(page.getByRole('button', { name: /^View / })).toHaveCount(4)
})

test('Dictionary creates a real deck in a nested destination with the selected sense', async ({ page, nodes }) => {
  const folder = await nodes.create({ type: 'folder' })
  const name = 'dictionary-' + randomUUID()
  await page.goto('/app/dictionary?q=bank')
  await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText('Free plan')
  await page.getByRole('button', { name: 'bank Ready', exact: true }).click()
  await page.getByRole('button', { name: 'Add to deck', exact: true }).first().click()
  const destination = page.getByRole('dialog', { name: 'Choose a destination' })
  await destination.getByRole('button', { name: 'Personal', exact: true }).dblclick()
  await destination.getByRole('button', { name: folder.name, exact: true }).dblclick()
  await destination.getByRole('button', { name: `Create a deck in ${folder.name}`, exact: true }).click()
  await destination.getByRole('textbox', { name: 'New deck name' }).fill(name)
  const created = page.waitForResponse(r => r.url().endsWith('/v1/nodes') && r.request().method() === 'POST')
  await destination.getByRole('button', { name: 'Create and add', exact: true }).click()
  const response = await created
  expect(response.status()).toBe(201)
  const deck = await response.json(); nodes.track(deck.id)
  expect(deck.parent_id).toBe(folder.id)
  expect(deck.sense_ids).toEqual([1])
  await page.goto(`/app/personal/${deck.id}/words`)
  await expect(page.getByRole('button', { name: /^View bank:/ })).toHaveCount(1)
})

test('Dictionary native aliases and inflections reveal POS tabs, lexical detail and related navigation', async ({ page }) => {
  await signIn(page)
  await page.goto('/app/dictionary?q=bank-alt')
  await page.getByRole('button', { name: /bank.*Ready/ }).click()
  await expect(page.getByText(/Also spelled.*bank-alt/i)).toBeVisible()
  await page.getByRole('tab', { name: /^verb/i }).click()
  await expect(page.getByRole('heading', { name: 'to deposit money in a financial institution', exact: true })).toBeVisible()
  await expect(page.getByText('banking', { exact: true })).toBeVisible()
  await expect(page.getByText(/bank a cheque/)).toBeVisible()
  await expect(page.getByText('Patterns', { exact: true })).toBeVisible()
  await page.getByRole('searchbox', { name: 'Search word or expression' }).fill('banking')
  await page.getByRole('button', { name: /bank.*Matched.*banking/ }).click()
  await page.getByRole('button', { name: /archive.*word family/i }).click()
  await expect(page.getByRole('heading', { name: 'archive', exact: true })).toBeVisible()
})
