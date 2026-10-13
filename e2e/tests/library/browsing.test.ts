import { test, expect } from '../../fixtures/index.ts'

test('nested words paginate and URL history preserves filters across reload', async ({ actor, data, vocabulary }) => {
  const folder = await data.create({ name: 'Academic topics', type: 'folder' })
  const deck = await data.create({ name: 'Distinct academic meanings', type: 'deck', parent_id: folder.id, sense_ids: vocabulary.pagination.slice(0, 25).map(item => item.sense_id) })
  await actor.page.goto(`/app/personal/${deck.id}/words`)
  await expect(actor.page.getByRole('navigation', { name: 'breadcrumb' })).toContainText(folder.name)
  const rows = actor.page.getByRole('table').getByRole('row').filter({ has: actor.page.locator('td') })
  await expect(rows).toHaveCount(12)
  const firstPage = await rows.allTextContents()
  await actor.page.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(actor.page).toHaveURL(/cursor=/)
  await expect(rows).toHaveCount(12)
  await expect.poll(async () => (await rows.allTextContents()).some(value => firstPage.includes(value))).toBe(false)
  const secondPage = await rows.allTextContents()
  expect(secondPage.some(value => firstPage.includes(value))).toBe(false)
  await actor.page.reload()
  await expect(rows).toHaveText(secondPage)
  await actor.page.getByRole('button', { name: 'Previous page', exact: true }).click()
  await expect(rows).toHaveText(firstPage)
  await actor.page.getByRole('searchbox', { name: 'Search words', exact: true }).fill(vocabulary.pagination[0].lemma)
  await expect(actor.page).toHaveURL(/q=/)
  await expect(actor.page.getByRole('table')).toContainText(vocabulary.pagination[0].definition)
  await actor.page.getByRole('radio', { name: /^Not yet due/ }).click()
  await expect(actor.page).toHaveURL(/state=not_yet_due/)
  await expect(actor.page.getByRole('table')).not.toBeVisible()
  await actor.page.goBack()
  await expect(actor.page.getByRole('table')).toContainText(vocabulary.pagination[0].definition)
})

test('a delayed native search cannot replace the results of a newer search', async ({ actor, data }) => {
  const earlier = await data.create({ name: 'Earlier river words', type: 'deck' })
  const later = await data.create({ name: 'Later mountain words', type: 'deck' })
  let release!: () => void
  let received!: () => void
  let completed!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const held = new Promise<void>(resolve => { received = resolve })
  const settled = new Promise<void>(resolve => { completed = resolve })
  await actor.page.route('**/v1/nodes/*:search?**', async route => {
    if (new URL(route.request().url()).searchParams.get('q') !== 'Earlier') return route.continue()
    try {
      const response = await route.fetch()
      received()
      await gate
      await route.fulfill({ response })
    } finally { completed() }
  })
  try {
    await actor.page.goto('/app/personal')
    const search = actor.page.getByRole('searchbox', { name: 'Search this folder', exact: true })
    await search.fill('Earlier')
    await held
    await search.fill('Later')
    await expect(actor.page.getByRole('heading', { name: later.name, exact: true })).toBeVisible()
    release()
    await settled
    await expect(actor.page.getByRole('heading', { name: earlier.name, exact: true })).not.toBeVisible()
    await expect(actor.page.getByRole('heading', { name: later.name, exact: true })).toBeVisible()
    await expect(actor.page).toHaveURL(/q=Later/)
  } finally { release() }
})
