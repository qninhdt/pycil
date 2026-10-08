import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { flashcardArtwork } from '../src/lib/flashcard-artwork'

test('Canonical node routes default to Overview; Words supports direct loads, reloads and browser history', async ({ page }) => {
  for (const node of ['everyday', 'business', 'travel', 'saved-business']) {
    await page.goto(`/app/personal/${node}`)
    await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('data-state', 'active')
    await expect(page.getByRole('tab', { name: 'Meanings', exact: true })).toHaveCount(0)
    await expect(page.getByRole('navigation', { name: 'App navigation' }).getByRole('link', { name: 'My Library', exact: true })).toHaveAttribute('aria-current', 'page')
  }
  await page.goto('/app/personal/everyday/words')
  await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('data-state', 'active')
  await expect(page.getByRole('searchbox', { name: 'Search words', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('data-state', 'active')
  await page.getByRole('tab', { name: 'Overview', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/personal\/everyday$/)
  await expect(page.getByRole('region', { name: 'Flashcard preview' })).toBeVisible()
  await page.goBack()
  await expect(page).toHaveURL(/\/app\/personal\/everyday\/words$/)
  await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('data-state', 'active')
  await page.goForward()
  await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('data-state', 'active')
})

test('Legacy query links redirect to canonical paths without reviving the old tab names', async ({ page }) => {
  for (const [query, path, tab] of [
    ['node=everyday', '/everyday', 'Overview'],
    ['node=everyday&tab=meanings', '/everyday/words', 'Words'],
    ['node=business&tab=words', '/business/words', 'Words'],
    ['node=business&tab=overview', '/business', 'Overview'],
  ]) {
    await page.goto(`/app/personal?${query}`)
    await expect(page).toHaveURL(new RegExp(`/app/personal${path}$`))
    await expect(page.getByRole('tab', { name: tab, exact: true })).toHaveAttribute('data-state', 'active')
  }
})

test('Overview and Words tabs have no outer outline or ring but keep a keyboard focus cue', async ({ page }) => {
  await page.goto('/app/personal/everyday')
  await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toBeVisible()
  for (const dark of [false, true]) {
    await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
    for (const name of ['Overview', 'Words']) {
      const tab = page.getByRole('tab', { name, exact: true })
      await page.keyboard.press('Tab')
      await tab.focus()
      await expect.poll(() => tab.evaluate(node => {
        const style = getComputedStyle(node)
        return { outline: style.outlineStyle, shadow: style.boxShadow, keyboard: node.matches(':focus-visible'), underline: getComputedStyle(node, '::after').opacity }
      })).toEqual({ outline: 'none', shadow: 'none', keyboard: true, underline: '1' })
    }
  }
  await page.getByRole('tab', { name: 'Words', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/personal\/everyday\/words$/)
})

test('Words route supports filters, pagination and node actions without personal requests', async ({ page }) => {
  const external: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    if (url.pathname.startsWith('/api/v1/') || url.origin !== new URL(test.info().project.use.baseURL!).origin) external.push(request.url())
  })
  await page.goto('/app/personal/everyday/words')
  await expect(page.getByRole('heading', { name: 'Everyday conversation', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Words', exact: true })).toHaveAttribute('data-state', 'active')
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.locator('.library-meaning-table tbody tr')).toHaveCount(12)
  await page.getByRole('button', { name: 'Settings for Everyday conversation' }).click()
  await expect(page.getByRole('menuitem', { name: 'Edit details' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: 'Add words', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Next page', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Pagination' })).toContainText('Page 2')
  await page.getByRole('button', { name: 'Previous page', exact: true }).click()
  await expect(page.getByRole('navigation', { name: 'Pagination' })).toContainText('Page 1')
  await page.getByRole('radiogroup', { name: 'Learning state' }).getByRole('radio', { name: /^Due,/ }).click()
  await expect(page.locator('.library-meaning-table tbody tr')).toHaveCount(9)
  await expect(page.locator('.library-state-cell')).toHaveText(Array(9).fill('Due'))
  await page.getByRole('radiogroup', { name: 'Learning state' }).getByRole('radio', { name: /^All words,/ }).click()
  await page.getByRole('searchbox', { name: 'Search words', exact: true }).fill('bank')
  await expect(page.locator('.library-meaning-table tbody tr')).toHaveCount(2)
  await expect(page.locator('.library-definition-cell')).toContainText(['an organization', 'the land'])
  await page.getByRole('searchbox', { name: 'Search words', exact: true }).fill('not-a-word')
  await expect(page.getByText('No matching words.', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Clear filters', exact: true }).click()
  await expect(page.locator('.library-meaning-table tbody tr')).toHaveCount(12)
  expect(external).toEqual([])
})

test('Folder starts with overview, supports nested browsing, a source-free word table and browser Back', async ({ page }) => {
  await page.goto('/app/personal/business')
  await expect.poll(() => page.locator('.library-contents-toolbar svg.bauhaus-icon--control').first().evaluate(node => node.getBoundingClientRect().width)).toBeLessThanOrEqual(24)
  await expect(page.getByRole('heading', { name: 'Business English', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('data-state', 'active')
  await expect(page.locator('section[aria-labelledby="library-subfolders-title"] > .library-node-grid > li')).toHaveCount(3)
  await page.getByRole('link', { name: /Business Core.*Deck/ }).click()
  await expect(page.getByRole('heading', { name: 'Business Core', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/app\/personal\/business-core$/)
  await expect(page.getByRole('tab', { name: 'Overview', exact: true })).toHaveAttribute('data-state', 'active')
  await page.goBack()
  await expect(page.getByRole('heading', { name: 'Business English', exact: true })).toBeVisible()
  await page.getByRole('tab', { name: 'Words', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/personal\/business\/words$/)
  await expect(page.getByRole('columnheader', { name: 'Source decks' })).toHaveCount(0)
  await expect(page.locator('.library-source-cell')).toHaveCount(0)
  const agenda = page.locator('.library-meaning-table tbody tr').filter({ has: page.getByRole('button', { name: /^View agenda:/ }) })
  await agenda.getByRole('button', { name: /^View agenda:/ }).click()
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Business Core', exact: true })).toBeVisible()
  await expect(page.getByRole('dialog').getByRole('link', { name: 'Meeting expressions', exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: 'Overview', exact: true }).click()
  await page.getByRole('searchbox', { name: 'Search this folder', exact: true }).fill('Email')
  await expect(page.getByRole('link', { name: /Email essentials/ })).toBeVisible()
})

test('Word detail is keyboard accessible, closes back to its trigger and does not merge different senses', async ({ page }) => {
  await page.goto('/app/personal/everyday/words')
  await page.getByRole('searchbox', { name: 'Search words' }).fill('bank')
  const bank = page.getByRole('button', { name: /^View bank: an organization/ })
  await bank.focus()
  await page.keyboard.press('Enter')
  const detail = page.getByRole('dialog')
  await expect(detail.getByRole('heading', { name: 'bank', exact: true })).toBeVisible()
  await expect(detail).toContainText('She deposited the money at the bank.')
  await expect(detail.locator('blockquote mark')).toHaveText(['bank', 'bank'])
  await page.keyboard.press('Escape')
  await expect(detail).toHaveCount(0)
  await expect(bank).toBeFocused()
  await page.getByRole('button', { name: /^View bank: the land/ }).click()
  await expect(detail).toContainText('They sat on the river bank.')
})

test('Study actions route to fullscreen focus mode without preparing questions on Library', async ({ page }) => {
  const studyRequests: string[] = []
  page.on('request', request => { if (request.url().includes('/api/v1/study/')) studyRequests.push(request.url()) })
  await page.goto('/app/personal/business-core')
  await expect(page.getByRole('heading', { name: 'Deck details' })).toBeVisible()
  const preview = page.getByRole('region', { name: 'Flashcard preview' })
  await expect(preview.locator('article[data-face=front]')).toBeVisible()
  await expect(page.getByRole('link', { name: /^Flashcards / })).toHaveAttribute('href', '/focus/flashcards?node=business-core')
  await expect(page.getByRole('link', { name: /^Learn new / })).toHaveAttribute('href', '/focus/learn?node=business-core&selection=NEW')
  await page.getByRole('link', { name: /^Review / }).click()
  await expect(page).toHaveURL(/\/focus\/learn\?node=business-core&selection=DUE$/)
  await expect(page.getByRole('button', { name: 'Start session' })).toBeVisible()
  await expect(page.locator('.shell-desktop, .library-inline-preview, .home-session')).toHaveCount(0)
  expect(studyRequests).toEqual([])
})

test('Deck preview reuses the two-face card, supports keyboard and crosses page boundaries without submitting learning', async ({ page }) => {
  const requests: string[] = []
  page.on('request', request => { if (request.method() === 'POST' || request.url().includes('/api/v1/')) requests.push(request.url()) })
  await page.goto('/app/personal/everyday')
  const preview = page.getByRole('region', { name: 'Flashcard preview' })
  const card = preview.locator('article')
  await expect(preview.getByRole('status')).toHaveText('1 / 36')
  const firstArtwork = await card.getAttribute('data-artwork')
  const firstGeometry = await card.getAttribute('style')
  const firstSvg = await card.locator('svg.bauhaus-background').evaluate(node => node.outerHTML)
  const firstBounds = await card.locator('svg.bauhaus-background').boundingBox()
  const posBounds = await card.getByText('verb', { exact: true }).boundingBox()
  const longWordSize = await card.locator('h3:visible').evaluate(node => parseFloat(getComputedStyle(node).fontSize))
  expect(await card.evaluate(node => getComputedStyle(node).borderRadius)).toBe('0px')
  await expect(card.locator('svg.bauhaus-background')).toHaveAttribute('preserveAspectRatio', 'xMidYMid meet')
  expect(await card.locator('svg.bauhaus-background').evaluate(node => {
    const overlay = getComputedStyle(node.parentElement!, '::after')
    return { inset: overlay.inset, background: overlay.backgroundColor }
  })).toEqual({ inset: '0px', background: expect.stringMatching(/(?:0\.82|82%)/) })
  await expect(preview.getByRole('button', { name: 'Previous flashcard' })).toBeDisabled()
  const reveal = preview.getByRole('button', { name: /^Reveal meaning of / })
  await reveal.focus()
  await page.keyboard.press('Space')
  await expect(card).toHaveAttribute('data-face', 'back')
  expect(await card.getByText('verb', { exact: true }).boundingBox()).toEqual(posBounds)
  await expect(preview.getByRole('blockquote')).toHaveCount(1)
  await expect(card.locator('blockquote mark:visible')).toHaveText('acknowledge')
  expect(await card.locator('svg.bauhaus-background').evaluate(node => node.outerHTML)).toBe(firstSvg)
  expect(await card.locator('svg.bauhaus-background').boundingBox()).toEqual(firstBounds)
  await expect(card).toHaveAttribute('data-artwork', firstArtwork!)
  await expect(preview.getByRole('button', { name: 'Next card', exact: true })).toHaveCount(0)
  await expect(preview.getByRole('button', { name: 'Show word', exact: true })).toHaveCount(0)
  await expect(preview.getByRole('button', { name: /^Flip back to word / })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(card).toHaveAttribute('data-face', 'front')
  await reveal.click()
  await preview.getByRole('button', { name: /^Flip back to word / }).click()
  await expect(card).toHaveAttribute('data-face', 'front')
  await reveal.focus()
  await page.keyboard.press('ArrowRight')
  await expect(preview.getByRole('status')).toHaveText('2 / 36')
  await expect(card).toHaveAttribute('data-artwork', flashcardArtwork(38))
  await expect.poll(() => card.locator('h3:visible').evaluate(node => parseFloat(getComputedStyle(node).fontSize))).toBeGreaterThan(longWordSize)
  expect(await card.getAttribute('style')).not.toBe(firstGeometry)
  for (let index = 2; index < 13; index++) {
    await preview.getByRole('button', { name: 'Next flashcard', exact: true }).click()
    await expect(preview.getByRole('status')).toHaveText(`${index + 1} / 36`)
  }
  await preview.getByRole('button', { name: 'Previous flashcard', exact: true }).click()
  await expect(preview.getByRole('status')).toHaveText('12 / 36')
  await expect(card).toHaveAttribute('data-face', 'front')
  await preview.getByRole('button', { name: /^Reveal meaning of / }).click()
  await preview.getByRole('button', { name: 'Next flashcard', exact: true }).click()
  await expect(preview.getByRole('status')).toHaveText('13 / 36')
  await expect(card).toHaveAttribute('data-face', 'front')
  await page.reload()
  await expect(preview.getByRole('status')).toHaveText('1 / 36')
  await expect(card).toHaveAttribute('data-artwork', firstArtwork!)
  await expect(card).toHaveAttribute('style', firstGeometry!)
  expect(requests).toEqual([])
})

test('References retain deck/folder identities in Library and Home, with no generic reference icon or section suffix', async ({ page }) => {
  await page.goto('/app/personal')
  await expect(page.getByRole('heading', { name: 'Decks', exact: true })).toBeVisible()
  const travel = page.getByRole('link', { name: /Travel essentials.*Deck reference/ })
  await expect(travel.locator('[data-art-icon=deck-reference]')).toBeVisible()
  await expect(page.getByRole('heading', { name: /& references/ })).toHaveCount(0)
  const businessReference = page.getByRole('link', { name: /Business collection.*Folder reference/ })
  await expect(businessReference.locator('[data-art-icon=folder-reference]')).toBeVisible()
  await businessReference.click()
  await expect(page.getByRole('heading', { name: 'Business collection', exact: true })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Overview' })).toHaveAttribute('data-state', 'active')
  await expect(page.getByRole('link', { name: 'Open source', exact: true })).toHaveAttribute('href', '/app/personal/business')
  await expect(page.locator('section[aria-labelledby="library-subfolders-title"] > .library-node-grid > li')).toHaveCount(3)
  await page.getByRole('tab', { name: 'Words', exact: true }).click()
  await expect(page.getByRole('columnheader', { name: 'Source decks' })).toHaveCount(0)
  await page.goto('/app/personal/emails')
  const meetings = page.locator('.library-node-item').filter({ hasText: 'Meeting notes' })
  await expect(meetings.locator('[data-art-icon=folder-reference]')).toBeVisible()
  await expect(meetings).toContainText('Folder reference')
  await meetings.getByRole('link').click()
  await expect(page.getByRole('tab', { name: 'Overview' })).toHaveAttribute('data-state', 'active')
  await expect(page.getByRole('link', { name: /Meeting expressions.*Deck/ })).toBeVisible()
  await page.goto('/app')
  await expect(page.getByRole('link', { name: /Travel essentials.*Deck reference/ }).locator('[data-art-icon=deck-reference]')).toBeVisible()
  await expect(page.getByRole('link', { name: /Business collection.*Folder reference/ }).locator('[data-art-icon=folder-reference]')).toBeVisible()
  await expect(page.locator('[data-art-icon=link]')).toHaveCount(0)
})

test('Bottom menus have no outer focus frame, preserve a keyboard cue, and sign out has a Bauhaus icon', async ({ page }) => {
  await page.goto('/app/personal')
  for (const name of ['New deck / folder', 'Open account menu']) {
    const trigger = page.getByRole('button', { name, exact: true })
    await trigger.click()
    await expect(page.getByRole('menu')).toBeVisible()
    if (name === 'Open account menu') await expect(page.getByRole('menuitem', { name: 'Sign out', exact: true }).locator('[data-art-icon=sign-out]')).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
    expect(await trigger.evaluate(node => getComputedStyle(node).outlineStyle)).toBe('none')
    await page.keyboard.press('Tab')
    await trigger.focus()
    expect(await trigger.evaluate(node => node.matches(':focus-visible'))).toBe(true)
    expect(await trigger.evaluate(node => getComputedStyle(node).boxShadow)).not.toBe('none')
  }
})

test('References, empty decks and missing material keep distinct truthful states', async ({ page }) => {
  await page.goto('/app/personal/travel')
  await expect(page.getByRole('heading', { name: 'Travel essentials', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'Open source', exact: true })).toHaveAttribute('href', '/app/u/preview-sam/published/travel-source')
  await expect(page.getByRole('button', { name: 'Add words', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: 'Open source', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Edit deck', exact: true })).toHaveCount(0)
  await page.goto('/app/personal/unavailable-reference')
  await expect(page.getByText('Reference unavailable.', { exact: true })).toBeVisible()
  await expect(page.locator('.library-summary')).toHaveCount(0)
  await page.goto('/app/personal/empty-deck/words')
  await expect(page.getByText('No words here yet.', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Review / })).toBeDisabled()
  await expect(page.getByRole('button', { name: /^Learn new / })).toBeDisabled()
  await expect(page.getByRole('button', { name: /^Flashcards / })).toBeDisabled()
  await page.goto('/app/personal/missing')
  await expect(page.locator('.library-page').getByRole('alert')).toContainText('This material could not be found.')
  await expect(page.locator('.library-summary')).toHaveCount(0)
})

test('Personal and Published have separate navigation and ownership breadcrumbs', async ({ page }) => {
  await page.goto('/app')
  await page.getByRole('link', { name: /Everyday conversation.*Deck/ }).click()
  await expect(page.getByRole('heading', { name: 'Everyday conversation', exact: true })).toBeVisible()
  await page.goto('/app/personal')
  await expect(page.getByRole('heading', { name: 'Personal', exact: true })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Personal')
  await expect(page.getByRole('navigation', { name: 'Library spaces' })).toHaveCount(0)
  const navigation = page.getByRole('navigation', { name: 'App navigation' })
  await expect(navigation.getByRole('link')).toHaveText(['Home', 'My Library', 'Published', 'Discovery', 'Dictionary'])
  await expect(navigation.getByRole('link', { name: 'Published', exact: true }).locator('[data-art-icon=published]')).toBeVisible()
  await navigation.getByRole('link', { name: 'Published', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/u\/preview-alex\/published$/)
  await expect(page.getByRole('heading', { name: 'Published', exact: true })).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Me')
  await expect(navigation.getByRole('link', { name: 'Published', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('link', { name: /A few useful expressions.*Deck/ })).toBeVisible()
  await page.goto('/app/u/preview-sam/published/travel-source')
  await expect(navigation.getByRole('link', { name: 'Discovery', exact: true })).toHaveAttribute('aria-current', 'page')
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Sam')
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).toContainText('Published')
  await expect(page.getByRole('navigation', { name: 'Breadcrumb' })).not.toContainText('Discovery')
})

test('Published word sources and author labels keep their owner route', async ({ page }) => {
  await page.goto('/app/u/preview-alex/published/published-everyday/words')
  await expect(page.getByText('By Me', { exact: true })).toBeVisible()
  await page.locator('.library-meaning-table tbody tr').first().getByRole('button').click()
  await expect(page.getByRole('dialog').getByRole('link', { name: 'A few useful expressions' })).toHaveAttribute('href', '/app/u/preview-alex/published/published-everyday')
  const response = await page.goto('/app/library')
  expect(response?.status()).toBe(404)
})

test('Library desktop/mobile and theme matrix stays within frame with usable meaning rows', async ({ page }) => {
  test.setTimeout(120_000)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const directory = process.env.LIBRARY_SCREENSHOT_DIR || '/tmp/opencode/pycil-library'
  mkdirSync(directory, { recursive: true })
  for (const width of [1852, 1440, 390, 320]) {
    await page.setViewportSize({ width, height: width === 1852 ? 935 : 1000 })
    for (const [name, route] of [['personal', 'preview-personal'], ['deck', 'everyday/words'], ['folder', 'business'], ['deck-overview', 'business-core'], ['folder-words', 'business/words']]) {
      await page.goto(`/app/personal/${route}`)
      await expect(page.locator('.library-summary')).toBeVisible()
      await expect(page.getByRole('tabpanel')).toBeVisible()
      if (name.includes('overview')) {
        await expect(page.getByRole('heading', { name: 'Deck details' })).toBeVisible()
        await expect(page.getByRole('region', { name: 'Flashcard preview' }).locator('article[data-face=front]')).toBeVisible()
      }
      else if (name === 'folder' || name === 'personal') await expect(page.locator('.library-node-grid').first()).toBeVisible()
      else await expect(page.locator('.library-meaning-table')).toBeVisible()
      for (const dark of [false, true]) {
        await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
        if (width === 1852) {
          const frame = await page.locator('.library-page').boundingBox()
          expect(frame!.width).toBeGreaterThan(1400)
          if (name === 'personal') {
            const firstDeck = await page.locator('section[aria-labelledby="library-decks-title"] > .library-node-grid > li').first().boundingBox()
            expect(firstDeck!.y + 80).toBeLessThan(935)
          }
          if (name === 'deck') {
            const rows = await page.locator('.library-meaning-table tbody tr').evaluateAll(nodes => nodes.filter(node => node.getBoundingClientRect().bottom <= innerHeight).length)
            expect(rows).toBeGreaterThanOrEqual(6)
          }
        }
        if (name === 'deck') {
          const contrast = () => page.locator('.library-state-filters [data-state=on] > span').evaluate(node => {
            const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1
            const ctx = canvas.getContext('2d')!
            const luminance = (color: string) => {
              ctx.fillStyle = color; ctx.fillRect(0, 0, 1, 1)
              const channels = [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3).map(value => { const n = value / 255; return n <= .04045 ? n / 12.92 : ((n + .055) / 1.055) ** 2.4 })
              return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
            }
            const foreground = luminance(getComputedStyle(node).color), background = luminance(getComputedStyle(node.parentElement!).backgroundColor)
            return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05)
          })
          await expect.poll(contrast).toBeGreaterThanOrEqual(4.5)
        }
        await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur() })
        await page.screenshot({ path: `${directory}/${name}-${width}-${dark ? 'dark' : 'light'}.png`, fullPage: true, animations: 'disabled' })
        if (name === 'deck-overview') {
          const preview = page.getByRole('region', { name: 'Flashcard preview' })
          const pos = preview.locator('article').getByText('verb', { exact: true })
          // A click can scroll a mobile card into view; compare in card coordinates.
          const posOffset = () => pos.evaluate(node => {
            const label = node.getBoundingClientRect(), card = node.closest('article')!.getBoundingClientRect()
            return { x: label.x - card.x, y: label.y - card.y, width: label.width, height: label.height }
          })
          const posBefore = await posOffset()
          await preview.getByRole('button', { name: /^Reveal meaning of / }).click()
          await expect(preview.locator('article[data-face=back]')).toBeVisible()
          expect(await posOffset()).toEqual(posBefore)
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
          await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur() })
          await page.screenshot({ path: `${directory}/flashcard-back-${width}-${dark ? 'dark' : 'light'}.png`, fullPage: true, animations: 'disabled' })
          await preview.getByRole('button', { name: /^Flip back to word / }).click()
          await preview.getByRole('button', { name: 'Next flashcard' }).click()
          await expect(preview.getByRole('status')).toHaveText('2 / 24')
          await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur() })
          await page.screenshot({ path: `${directory}/flashcard-second-${width}-${dark ? 'dark' : 'light'}.png`, fullPage: true, animations: 'disabled' })
          await preview.getByRole('button', { name: 'Previous flashcard' }).click()
        }
      }
    }
  }
  expect(errors).toEqual([])
})

test('Library creation, actions, and view preference work in mock mode', async ({ page }) => {
  await page.goto('/app/personal/business')
  const cards = page.locator('section[aria-labelledby="library-subfolders-title"] > .library-node-grid')
  await expect(cards).toHaveAttribute('data-view', 'cards')
  const motif = await cards.locator('.library-node-item').first().locator('.library-node-motif').getAttribute('data-motif')
  await page.getByRole('button', { name: 'List view' }).click()
  await expect(cards).toHaveAttribute('data-view', 'list')
  await page.reload()
  await expect(page.locator('section[aria-labelledby="library-subfolders-title"] > .library-node-grid')).toHaveAttribute('data-view', 'list')
  await page.getByRole('button', { name: 'Card view' }).click()
  await expect(page.locator('.library-node-motif').first()).toHaveAttribute('data-motif', motif!)

  await page.getByRole('button', { name: 'New folder' }).click()
  const form = page.getByRole('dialog', { name: 'New folder' })
  await expect(form.getByText('Business English', { exact: true })).toBeVisible()
  await expect.poll(() => form.locator('.library-destination-field svg').evaluate(node => node.getBoundingClientRect().width)).toBe(18)
  await expect(form.getByRole('button', { name: /Change/ })).toHaveCount(0)
  await form.getByRole('textbox', { name: 'Title' }).fill('Practice notes')
  await form.getByRole('textbox', { name: /Description/ }).fill('A place for examples')
  await form.getByRole('button', { name: 'Create folder' }).click()
  await expect(page.getByRole('heading', { name: 'Practice notes', exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Settings for Practice notes' }).click()
  await page.getByRole('menuitem', { name: 'Edit details' }).click()
  const edit = page.getByRole('dialog', { name: 'Edit folder' })
  await edit.getByRole('textbox', { name: 'Title' }).fill('Practice archive')
  await edit.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByRole('heading', { name: 'Practice archive', exact: true })).toBeVisible()

  await page.goto('/app/personal?create=deck')
  const newDeck = page.getByRole('dialog', { name: 'New deck' })
  await newDeck.getByRole('button', { name: /Personal.*Change/ }).click()
  const picker = page.getByRole('dialog', { name: 'Choose a destination' })
  await picker.getByRole('button', { name: 'Published', exact: true }).click()
  await picker.getByRole('button', { name: 'Use this folder' }).click()
  await expect(newDeck.getByRole('button', { name: /Published.*Change/ })).toBeVisible()
  await newDeck.getByRole('textbox', { name: 'Title' }).fill('Published practice')
  await newDeck.getByRole('checkbox', { name: 'Make this deck publicly readable.' }).check()
  await newDeck.getByRole('button', { name: 'Create deck' }).click()
  await expect(page).toHaveURL(/\/app\/u\/preview-alex\/published\/preview-deck-/)
  await expect(page.getByRole('heading', { name: 'Published practice', exact: true })).toBeVisible()
})
