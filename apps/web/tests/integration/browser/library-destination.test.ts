import { expect,test,type Page } from '@playwright/test'

import { buildFixture,renderFixture } from './fixtures/render-fixture'

let bundle: string

test.beforeAll(async () => { bundle = await buildFixture('library-destination') })

async function openPicker(page: Page) {
  const messages: string[] = [], saved: string[] = []
  page.on('console', message => { if (message.type() === 'error') messages.push(message.text()) })
  page.on('pageerror', error => messages.push(error.message))
  const nodes = {
    library: { id: 'library', name: 'My Library', type: 'folder', parent: null, space: 'library' },
    personal: { id: 'personal', name: 'Personal', type: 'folder', parent: 'library', space: 'personal' },
    published: { id: 'published', name: 'Published', type: 'folder', parent: 'library', space: 'published' },
    reference: { id: 'reference', name: 'hello', type: 'reference', parent: 'personal', space: 'personal', reference_id: 'hello' },
    foreignReference: { id: 'foreignReference', name: 'Saved foreign deck', type: 'reference', parent: 'personal', space: 'personal', reference_id: 'foreign' },
    nested: { id: 'nested', name: 'Nested folder', type: 'folder', parent: 'published', space: 'published' },
    hello: { id: 'hello', name: 'hello', type: 'deck', parent: 'nested', space: 'published' },
    foreign: { id: 'foreign', name: 'Foreign deck', type: 'deck', parent: null, space: 'published', owner_id: 'other-account' },
  } satisfies Record<string, { id: string; name: string; type: string; parent: string | null; space: string; reference_id?: string; owner_id?: string }>
  const entries: Record<string, typeof nodes[keyof typeof nodes] & { owner_id?: string; reference_id?: string }> = nodes
  const metadata = (id: string) => {
    const node = entries[id], breadcrumbs = []
    for (let current: typeof node | undefined = node; current; current = current.parent ? entries[current.parent] : undefined) {
      breadcrumbs.unshift({ id: current.id, name: current.name })
    }
    return { ...node, owner_id: node.owner_id ?? 'test-account', description: null, role: 'normal', breadcrumbs,
      created_at: '2026-10-12T00:00:00Z', updated_at: '2026-10-12T00:00:00Z', reference_id: node.reference_id ?? null,
      reference_available: node.type === 'reference' ? true : null }
  }
  await page.route('**/*v1/**', route => {
    const url = new URL(route.request().url())
    expect(route.request().headers().authorization).toBe('Bearer test-only-bearer')
    if (url.pathname.endsWith(':modifySenses')) {
      saved.push(url.pathname)
      expect(route.request().postDataJSON()).toEqual({ add: [49], remove: [] })
      return route.fulfill({ json: { ok: true } })
    }
    if (url.pathname.endsWith('/nodes') || url.pathname.endsWith(':search')) {
      const children = url.pathname.endsWith(':search') ? [entries.nested] : Object.values(entries).filter(node => node.parent === url.searchParams.get('parent_id'))
      return route.fulfill({ json: { nodes: children.map(node => ({ ...metadata(node.id), summary: null,
        target_type: node.type === 'reference' ? 'deck' : null })), next_cursor: null } })
    }
    if (url.pathname.endsWith('/study/progress')) return route.fulfill({ json: {
      node_id: url.searchParams.get('node_id'), as_of: '2026-10-12T00:00:00Z', total: 0, new: 0,
      studied: 0, due: 0, not_due: 0, reachable_decks: 0, last_studied_at: null,
    } })
    const id = url.pathname.split('/').at(-1)!
    if (entries[id]) return route.fulfill({ json: metadata(id) })
    throw new Error(`Unexpected destination request: ${url}`)
  })
  await renderFixture(page, bundle, 'destination')
  return { picker: page.getByRole('dialog', { name: 'Choose a destination' }), messages, saved }
}

test('Personal and Published open with one click and each breadcrumb appears once', async ({ page }) => {
  const { picker, messages } = await openPicker(page)
  const path = picker.getByRole('navigation', { name: 'Destination path' })
  await picker.getByRole('button', { name: 'Personal', exact: true }).click()
  await expect(path.getByRole('button')).toHaveText(['My Library', 'Personal'])
  await expect(picker.getByRole('button', { name: 'hello Deck' })).toBeVisible()
  await path.getByRole('button', { name: 'My Library' }).click()
  await picker.getByRole('button', { name: 'Published', exact: true }).click()
  await expect(path.getByRole('button')).toHaveText(['My Library', 'Published'])
  await picker.getByRole('button', { name: 'Nested folder', exact: true }).click()
  await expect(path.getByRole('button')).toHaveText(['My Library', 'Published', 'Nested folder'])
  await expect(picker.getByRole('button', { name: 'hello Deck' })).toBeVisible()
  expect(messages).toEqual([])
  await page.setViewportSize({ width: 390, height: 844 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
})

test('an owned deck reference adds the sense to its canonical deck ID', async ({ page }) => {
  const { picker, saved } = await openPicker(page)
  await picker.getByRole('button', { name: 'Personal', exact: true }).click()
  await picker.getByRole('button', { name: 'hello Deck' }).click()
  await expect(picker.getByText('Selected: hello', { exact: true })).toBeVisible()
  await picker.getByRole('button', { name: 'Add to deck', exact: true }).click()
  await expect(page.locator('output')).toHaveText('hello')
  expect(saved[0].endsWith('/nodes/hello:modifySenses')).toBe(true)
})

test('a saved foreign deck is readable but cannot become an editing destination', async ({ page }) => {
  const { picker, saved } = await openPicker(page)
  await picker.getByRole('button', { name: 'Personal', exact: true }).click()
  await picker.getByRole('button', { name: 'Saved foreign deck Deck' }).click()
  await expect(picker.getByRole('alert')).toContainText('belongs to you')
  await expect(picker.getByRole('button', { name: 'Add to deck', exact: true })).toBeDisabled()
  expect(saved).toEqual([])
})

test('search navigation preserves the full path and returning to root clears the filter', async ({ page }) => {
  const { picker, messages } = await openPicker(page)
  await picker.getByRole('textbox', { name: 'Search folders and decks' }).fill('Nested')
  await picker.getByRole('button', { name: 'Nested folder', exact: true }).click()
  const path = picker.getByRole('navigation', { name: 'Destination path' })
  await expect(path.getByRole('button')).toHaveText(['My Library', 'Published', 'Nested folder'])
  await picker.getByRole('textbox', { name: 'Search folders and decks' }).fill('Missing')
  await path.getByRole('button', { name: 'My Library' }).click()
  await expect(picker.getByRole('textbox', { name: 'Search folders and decks' })).toHaveValue('')
  await expect(picker.getByRole('button', { name: 'Personal', exact: true })).toBeVisible()
  expect(messages).toEqual([])
})
