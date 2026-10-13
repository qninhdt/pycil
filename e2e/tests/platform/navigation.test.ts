import { test, expect } from '../../fixtures/index.ts'
import { apiURL, webURL } from '../../support/environment.ts'

test('hydrated Library filters call Pycil directly and preserve URL history', async ({ actor, data }) => {
  const first = await data.create({ type: 'deck', name: `Rivers ${actor.subject.slice(-8)}` })
  await data.create({ type: 'deck', name: `Mountains ${actor.subject.slice(-8)}` })
  const { page } = actor
  const initialReads: string[] = []
  page.on('request', request => {
    if (new URL(request.url()).origin === apiURL && request.method() === 'GET' && new URL(request.url()).pathname === '/v1/nodes') initialReads.push(request.url())
  })
  await page.goto('/app/personal')
  await expect(page.getByRole('heading', { name: first.name, exact: true })).toBeVisible()
  const [response] = await Promise.all([
    page.waitForResponse(response => new URL(response.url()).origin === apiURL && response.url().includes(':search') && response.url().includes('q=Rivers')),
    page.getByRole('searchbox', { name: 'Search this folder' }).fill('Rivers'),
  ])
  expect(response.status()).toBe(200)
  expect(initialReads, 'Fresh server data must prevent an immediate browser listing read').toEqual([])
  expect(response.request().url()).not.toContain(webURL)
  await expect(page).toHaveURL(/q=Rivers/)
  await expect(page.getByRole('heading', { name: /Mountains/ })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: first.name, exact: true })).toBeVisible()
  await expect(page.getByRole('searchbox', { name: 'Search this folder' })).toHaveValue('Rivers')
})

test('mobile navigation restores focus on dismissal and opens the selected workspace', async ({ actor, browser }) => {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, baseURL: webURL, viewport: { width: 390, height: 844 }, storageState: await actor.page.context().storageState() })
  try {
    const page = await context.newPage()
    await page.goto('/app')
    const trigger = page.getByRole('button', { name: 'Open navigation', exact: true })
    await trigger.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
    await expect(trigger).toBeFocused()
    await trigger.click()
    await dialog.getByRole('link', { name: 'Dictionary', exact: true }).click()
    await expect(page).toHaveURL(/\/app\/dictionary$/)
    await expect(dialog).not.toBeVisible()
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Dictionary')
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  } finally { await context.close() }
})
