import { test, expect } from '../../fixtures/index.ts'
import { apiURL, webURL } from '../../support/environment.ts'

test('client Library filters call Pycil directly and preserve URL history', async ({ sharedUser, sharedData }) => {
  const first = await sharedData.create({ type: 'deck', name: `Rivers ${sharedUser.subject.slice(-8)}` })
  await sharedData.create({ type: 'deck', name: `Mountains ${sharedUser.subject.slice(-8)}` })
  const { page } = sharedUser
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
  expect(initialReads, 'Personal data loads directly in the browser').toHaveLength(1)
  expect(response.request().url()).not.toContain(webURL)
  await expect(page).toHaveURL(/q=Rivers/)
  await expect(page.getByRole('heading', { name: /Mountains/ })).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: first.name, exact: true })).toBeVisible()
  await expect(page.getByRole('searchbox', { name: 'Search this folder' })).toHaveValue('Rivers')
})

test('mobile navigation restores focus on dismissal and opens the selected workspace', async ({ sharedUser }) => {
  const { page } = sharedUser
  await page.setViewportSize({ width: 390, height: 844 })
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
  await expect(page).toHaveURL(/\/dictionary$/)
  await expect(dialog).not.toBeVisible()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Dictionary')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
