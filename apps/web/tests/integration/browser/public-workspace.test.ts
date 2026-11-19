import { expect, test } from '@playwright/test'

test('root tabs and direct Words routes share URL state, including Back and Forward', async ({ page }) => {
  for (const path of ['/app/personal', '/app/published', '/u/preview-sam/travel-source']) {
    await page.goto(path)
    await page.getByRole('tab', { name: 'Words', exact: true }).click()
    await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('data-state', 'active')
    const words = page.url()
    await page.reload()
    await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('data-state', 'active')
    await page.getByRole('tab', { name: 'Overview', exact: true }).click()
    await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('data-state', 'active')
    await page.goBack()
    await expect(page).toHaveURL(words)
    await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('data-state', 'active')
    await page.goForward()
    await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('data-state', 'active')
  }
})

test('guest public browsing preserves the shell and omits private navigation and learning state', async ({ page }) => {
  await page.goto('/u/preview-sam/travel-source?action=study')
  await expect(page).toHaveURL(/\/app\/learn\?node=travel-source&selection=auto&owner=preview-sam$/)
  await page.goto('/u/preview-sam/travel-source')
  await page.getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
  const nav = page.getByRole('navigation', { name: 'App navigation' })
  await expect(nav.getByRole('link')).toHaveCount(2)
  await expect(page.getByRole('button', { name: 'Open PycilAI' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'New deck / folder' })).toHaveCount(0)
  await expect(page.getByRole('region', { name: 'Flashcard preview' })).toBeVisible()
  await page.getByRole('tab', { name: 'Words', exact: true }).click()
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.getByRole('group', { name: 'Learning state' })).toHaveCount(0)
  await expect(page.getByRole('columnheader', { name: 'Status', exact: true })).toHaveCount(0)
  const practice = page.getByRole('link', { name: 'Practice', exact: true })
  expect(new URL(await practice.getAttribute('href') ?? '', page.url()).searchParams.get('returnTo')).toMatch(/\/words\?action=study$/)
  await page.getByRole('link', { name: 'Save to Personal', exact: true }).click()
  await expect(page).toHaveURL(/\/login\?returnTo=/)
  expect(new URL(page.url()).searchParams.get('returnTo')).toMatch(/\/words\?action=save$/)
})

test('public HTML and social cards expose lexical content without a login or script execution', async ({ request }) => {
  const response = await request.get('/u/preview-sam/travel-source/words', { headers: { 'User-Agent': 'Twitterbot' } })
  expect(response.status()).toBe(200)
  const html = await response.text()
  expect(html).toContain('<table')
  expect(html).toContain('name="robots" content="noindex, follow"')
  expect(html).toContain('rel="canonical"')
  expect(html).toContain('property="og:title"')
  const image = await request.get('/u/preview-sam/travel-source/opengraph-image')
  expect(image.status()).toBe(200)
  expect(image.headers()['content-type']).toBe('image/png')
  expect(image.headers()['cache-control']).toContain('no-store')
  const png = await image.body()
  expect(png.readUInt32BE(16)).toBe(1200)
  expect(png.readUInt32BE(20)).toBe(630)
  expect((await request.get('/u/preview-sam/no-such-node/opengraph-image')).status()).toBe(404)
})

test('public content stays visible with JavaScript disabled', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false })
  try {
    const page = await context.newPage()
    await page.goto('http://127.0.0.1:3100/u/preview-sam/travel-source/words')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Travel')
    await expect(page.getByRole('table')).toBeVisible()
  } finally { await context.close() }
})
