import { test, expect } from '../../fixtures/index.ts'
import { webURL } from '../../support/environment.ts'

test('personal pages load through the interactive client workspace', async ({ sharedUser, sharedData, vocabulary }) => {
  const deck = await sharedData.create({ type: 'deck', name: `Reading ${sharedUser.subject.slice(-8)}`, sense_ids: [vocabulary.bankFinancial.sense_id] })
  const page = sharedUser.page
  await page.goto(`/app/personal/${deck.id}`)
  await expect(page.getByRole('heading', { level: 1 })).toContainText(deck.name)
  await expect(page.getByText('Deck details', { exact: true })).toBeVisible()
  await page.goto(`/dictionary?q=bank&word=${vocabulary.bankFinancial.word_id}`)
  await expect(page.locator('article')).toContainText('an institution where people keep and borrow money')
  await page.goto('/app/settings')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Settings')
  await expect(page.getByLabel(/Time zone/)).toHaveValue(sharedUser.account.settings.timezone)
})

test('a public collection provides its actual meanings and resource title without JavaScript', async ({ sharedUser, sharedData, browser, vocabulary }) => {
  const deck = await sharedData.create({ name: 'Public river reading', type: 'deck', sense_ids: [vocabulary.bankRiver.sense_id] })
  await sharedUser.api.call(`nodes/${deck.id}:move`, 'POST', { parent_id: sharedUser.account.published_node_id, confirm_publication: true })
  const context = await browser.newContext({ ignoreHTTPSErrors: true, javaScriptEnabled: false, baseURL: webURL })
  try {
    const page = await context.newPage()
    await page.goto(`/u/${sharedUser.account.id}/${deck.id}`)
    await expect(page.getByRole('heading', { level: 1 })).toContainText(deck.name)
    await expect(page.getByRole('region', { name: 'Flashcard preview' })).toContainText('bank')
    await page.goto(`/u/${sharedUser.account.id}/${deck.id}/words`)
    await expect(page.getByRole('table')).toContainText('the ground along the side of a river')
    await expect(page.locator('link[rel=canonical]')).toHaveAttribute('href', new RegExp(`/u/${sharedUser.account.handle || sharedUser.account.id}/${deck.id}/words$`))
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

test('personal navigation reuses fresh browser queries', async ({ sharedUser, sharedData, vocabulary }) => {
  await sharedData.create({ type: 'deck', name: 'Cache navigation', sense_ids: [vocabulary.bankFinancial.sense_id] })
  const page = sharedUser.page
  await page.goto('/app')
  await expect(page.getByRole('link', { name: /Learn new/ }).first()).toBeVisible()
  await page.getByRole('navigation', { name: 'App navigation' }).getByRole('link', { name: 'Dictionary', exact: true }).click()
  await expect(page.getByRole('searchbox')).toBeVisible()
  const reads: string[] = []
  page.on('request', request => {
    if (/\/v1\/(?:me$|study\/(?:progress|activity|review-schedule)(?:\?|$))/.test(request.url())) reads.push(request.url())
  })
  await page.getByRole('navigation', { name: 'App navigation' }).getByRole('link', { name: 'Home', exact: true }).click()
  await expect(page.getByRole('link', { name: /Learn new/ }).first()).toBeVisible()
  expect(reads, 'Returning within the query freshness window must reuse browser data').toEqual([])
})
