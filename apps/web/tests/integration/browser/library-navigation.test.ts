import { buildFixture,renderFixture } from './fixtures/render-fixture'

const accountFixture = `import {useSyncExternalStore} from 'react';
let account={status:'loading',profile:null};
const listeners=new Set();
window.addEventListener('fixture-account',event=>{account=event.detail;for(const listener of listeners)listener()});
export function useAccount(){return useSyncExternalStore(listener=>{listeners.add(listener);return()=>listeners.delete(listener)},()=>account,()=>account)}`

import { expect,test } from '@playwright/test'


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
  await expect(page.getByRole('button', { name: /^Practice,/ })).toBeDisabled()
  await expect(page.getByRole('button', { name: /^Learn new,/ })).toBeDisabled()
  await expect(page.getByRole('button', { name: /^Flashcards,/ })).toBeDisabled()
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
          await preview.getByRole('button', { name: /^Flip back to word / }).click()
          await preview.getByRole('button', { name: 'Next flashcard' }).click()
          await expect(preview.getByRole('status')).toHaveText('2 / 24')
          await page.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur() })
          await preview.getByRole('button', { name: 'Previous flashcard' }).click()
        }
      }
    }
  }
  expect(errors).toEqual([])
})

for (const source of [{ id: 'everyday', name: 'Everyday conversation', width: 1440 }, { id: 'business', name: 'Business English', width: 390 }]) test(`Create reference links an owned ${source.id} without copying its contents`, async ({ page }) => {
  await page.setViewportSize({ width: source.width, height: 844 })
  await page.goto(`/app/personal/${source.id}`)
  await page.getByRole('button', { name: `Settings for ${source.name}` }).click()
  await expect(page.getByRole('menuitem')).toHaveText(['Copy link', 'Edit details', 'Move', 'Copy', 'Create reference', 'Publish', 'Delete'])
  await page.getByRole('menuitem', { name: 'Create reference', exact: true }).click()
  const form = page.getByRole('dialog', { name: 'Create reference', exact: true })
  await expect(form.getByRole('textbox', { name: 'Title', exact: true })).toHaveValue(source.name)
  await form.getByRole('textbox', { name: 'Title', exact: true }).fill('   ')
  await expect(form.getByRole('button', { name: 'Create reference', exact: true })).toBeDisabled()
  const name = `Linked ${source.name}`
  await form.getByRole('textbox', { name: 'Title', exact: true }).fill(name)
  await form.getByRole('button', { name: /Change/ }).click()
  const picker = page.getByRole('dialog', { name: 'Choose a destination' })
  await expect(picker.getByRole('navigation', { name: 'Destination path' }).getByRole('button')).toHaveText(['Personal'])
  await expect(picker.getByRole('button', { name: 'Published', exact: true })).toHaveCount(0)
  await picker.getByRole('button', { name: 'Use this folder', exact: true }).click()
  await expect(picker).toHaveCount(0)
  await expect(form).toBeVisible()
  await form.getByRole('button', { name: 'Create reference', exact: true }).click()
  await expect(form).toHaveCount(0)
  if (source.width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('navigation', { name: 'App navigation' }).getByRole('link', { name: 'My Library', exact: true }).click()
  await page.getByRole('link', { name: new RegExp(`Open ${name},`) }).click()
  await expect(page.getByRole('link', { name: 'Open source', exact: true })).toHaveAttribute('href', `/app/personal/${source.id}`)
})

test('loading identity waits; guest resolution reads public contents without private auth or summaries', async ({ page }) => {
  const bundle = await buildFixture('library', { '@/components/application/providers': accountFixture })
  const calls: { authorization?: string; include: string | null }[] = []
  await page.route('**/api/v1/**', route => {
    const request = route.request()
    expect(new URL(request.url()).pathname).toBe('/api/v1/nodes')
    calls.push({ authorization: request.headers().authorization, include: new URL(request.url()).searchParams.get('include') })
    return route.fulfill({ json: { nodes: [{ id: 'public', name: 'Published contents', type: 'DECK', description: null, summary: null }], next_cursor: null } })
  })
  await renderFixture(page, bundle, 'library')
  await expect(page.getByLabel('Query status')).toHaveText('pending')
  expect(calls).toEqual([])
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('fixture-account', { detail: { status: 'signed-out', profile: null } })))
  await expect(page.getByRole('listitem')).toHaveText(['Published contents'])
  expect(calls).toEqual([{ authorization: undefined, include: null }])
})

test('changing accounts removes pending private contents and late responses cannot restore the old scope', async ({ page }) => {
  const bundle = await buildFixture('library', { '@/components/application/providers': accountFixture })
  let release!: () => void
  const delayed = new Promise<void>(resolve => { release = resolve })
  let first!: () => void
  const requested = new Promise<void>(resolve => { first = resolve })
  let completed!: () => void
  const responded = new Promise<void>(resolve => { completed = resolve })
  let count = 0
  await page.route('**/api/v1/**', async route => {
    expect(route.request().headers().authorization).toBe('Bearer test-only-bearer')
    expect(new URL(route.request().url()).searchParams.get('include')).toBe('summary')
    const old = count++ === 0
    if (old) { first(); await delayed }
    await route.fulfill({ json: { nodes: [{ id: old ? 'a' : 'b', name: old ? 'Private account A' : 'Private account B', type: 'DECK', description: null, summary: null }], next_cursor: null } }).catch(error => {
      if (!route.request().failure()) throw error
    })
    if (old) completed()
  })
  await renderFixture(page, bundle, 'library')
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('fixture-account', { detail: { status: 'ready', profile: { id: 'A' } } })))
  await requested
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('fixture-account', { detail: { status: 'ready', profile: { id: 'B' } } })))
  await expect(page.getByRole('listitem')).toHaveText(['Private account B'])
  release()
  await responded
  await expect(page.getByRole('listitem')).toHaveText(['Private account B'])
  await expect(page.getByText('Private account A')).toHaveCount(0)
})
