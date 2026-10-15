import { test, expect } from '../../fixtures/index.ts'
import { webURL } from '../../support/environment.ts'

test('authenticated initial pages contain visible server-rendered data without JavaScript', async ({ user, browser, data, vocabulary }) => {
  const deck = await data.create({ type: 'deck', name: `Reading ${user.subject.slice(-8)}`, sense_ids: [vocabulary.bankFinancial.sense_id] })
  const context = await browser.newContext({ ignoreHTTPSErrors: true, javaScriptEnabled: false, baseURL: webURL, storageState: await user.page.context().storageState() })
  try {
    const page = await context.newPage()
    await page.goto(`/app/personal/${deck.id}`)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(deck.name)
    await expect(page.getByText('Deck details', { exact: true })).toBeVisible()
    await page.goto('/app')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
    await expect(page.getByRole('link', { name: /Learn new/ }).first()).toBeVisible()
    await page.goto(`/app/dictionary?q=bank&word=${vocabulary.bankFinancial.word_id}`)
    await expect(page.locator('article')).toContainText('an institution where people keep and borrow money')
    await page.goto('/app/settings')
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Settings')
    await expect(page.getByLabel(/Time zone/)).toHaveValue(user.account.settings.timezone)
  } finally { await context.close() }
})


test('a public collection provides its actual meanings and resource title without JavaScript', async ({ user, browser, data, vocabulary }) => {
  const deck = await data.create({ name: 'Public river reading', type: 'deck', sense_ids: [vocabulary.bankRiver.sense_id] })
  await user.api.call(`nodes/${deck.id}:move`, 'POST', { parent_id: user.account.published_node_id, confirm_publication: true })
  const context = await browser.newContext({ ignoreHTTPSErrors: true, javaScriptEnabled: false, baseURL: webURL })
  try {
    const page = await context.newPage()
    await page.goto(`/u/${user.account.id}/${deck.id}`)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(deck.name)
    await expect(page.getByText('the ground along the side of a river', { exact: true })).toBeVisible()
    await expect(page).toHaveTitle(new RegExp(deck.name))
  } finally { await context.close() }
})

test('server HTML follows request locale and explicit theme cookies', async ({ browser }) => {
  const context = await browser.newContext({ ignoreHTTPSErrors: true, javaScriptEnabled: false, baseURL: webURL, locale: 'en-US' })
  try {
    await context.addCookies([
      { name: 'NEXT_LOCALE', value: 'vi', url: webURL },
      { name: 'pycil-theme', value: 'dark', url: webURL },
    ])
    const page = await context.newPage()
    await page.goto('/')
    await expect(page.locator('html')).toHaveAttribute('lang', 'vi')
    await expect(page.locator('html')).toHaveClass(/dark/)
    await context.addCookies([
      { name: 'NEXT_LOCALE', value: 'en', url: webURL },
      { name: 'pycil-theme', value: 'light', url: webURL },
    ])
    await page.reload()
    await expect(page.locator('html')).toHaveAttribute('lang', 'en')
    await expect(page.locator('html')).not.toHaveClass(/dark/)
  } finally { await context.close() }
})

test('Home hydration reuses fresh server queries after the interactive shell is ready', async ({ user }) => {
  const reads: string[] = []
  user.page.on('request', request => {
    if (/\/v1\/(?:me$|study\/(?:progress|activity|review-schedule)(?:\?|$))/.test(request.url())) reads.push(request.url())
  })
  await user.page.goto('/app')
  await user.page.getByRole('button', { name: 'Open account menu', exact: true }).click()
  await expect(user.page.getByRole('menuitem', { name: 'Sign out', exact: true })).toBeVisible()
  expect(reads, 'Hydrated interactive shell must reuse server-provided queries').toEqual([])
})
