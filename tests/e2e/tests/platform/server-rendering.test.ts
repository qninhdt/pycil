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

test('public profiles, folders and decks expose resource metadata and share images without JavaScript', async ({ user, data, browser, vocabulary }) => {
  const author = 'Vocabulary publisher', bio = 'Read and practice the vocabulary I share.'
  await user.api.call('me/profile', 'PATCH', { display_name: author, bio })
  const folder = await data.create({ name: 'River collections', description: 'Vocabulary for exploring rivers.', type: 'folder' })
  const deck = await data.create({ name: 'River meanings', description: 'Learn the meanings along a river.', type: 'deck', parent_id: folder.id, sense_ids: [vocabulary.bankRiver.sense_id] })
  await user.api.call(`nodes/${folder.id}:move`, 'POST', { parent_id: user.account.published_node_id, confirm_publication: true })
  const context = await browser.newContext({ ignoreHTTPSErrors: true, javaScriptEnabled: false, baseURL: webURL, userAgent: 'Twitterbot' })
  try {
    const page = await context.newPage()
    const profilePath = `/u/${user.account.handle || user.account.id}`
    for (const [path, title, description] of [
      [profilePath, author, bio],
      [`${profilePath}/${folder.id}`, folder.name, 'Vocabulary for exploring rivers.'],
      [`${profilePath}/${deck.id}`, deck.name, 'Learn the meanings along a river.'],
    ] as const) {
      const response = await page.goto(path)
      expect(response?.status()).toBe(200)
      await expect(page.getByRole('heading', { level: 1 })).toContainText(title)
      await expect(page).toHaveTitle(`${title} — Pycil`)
      await expect(page.locator('head meta[name=description]')).toHaveAttribute('content', description)
      await expect(page.locator('head meta[property="og:title"]')).toHaveAttribute('content', title)
      await expect(page.locator('head meta[property="og:description"]')).toHaveAttribute('content', description)
      await expect(page.locator('head meta[name="twitter:description"]')).toHaveAttribute('content', description)
      await expect(page.locator('link[rel=canonical]')).toHaveAttribute('href', `https://pycil.qninhdt.com${path}`)
      const image = page.locator('head meta[property="og:image"]')
      await expect(image).toHaveAttribute('content', `https://pycil.qninhdt.com${path}/opengraph-image`)
      const png = await context.request.get(`${path}/opengraph-image`)
      expect(png.status()).toBe(200)
      expect(png.headers()['content-type']).toContain('image/png')
      const bytes = await png.body()
      expect(bytes.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
      expect([bytes.readUInt32BE(16), bytes.readUInt32BE(20)]).toEqual([1200, 630])
    }
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
