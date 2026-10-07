import { test, expect, type Page } from '@playwright/test'
import { build } from 'esbuild'
import { mkdirSync } from 'node:fs'
import { initialUiScript } from '../src/lib/ui-preferences'
import { HomeApiError, homeRequest, homeToken, parseActivity, parseLibrary, parsePreparation, parseSchedule, parseSummary } from '../src/lib/home-api'
import { monthCells, reportingDay, shiftDay, activityLevel } from '../src/lib/home-calendar'

const summary = { node_id: 'library-root', as_of: '2026-10-07T02:00:00Z', total: 142, new: 46, studied: 96, due: 12, not_due: 84, last_studied_at: '2026-10-06T02:00:00Z', reachable_decks: 4 }
let bundle: string

test.beforeAll(async () => {
  const result = await build({ entryPoints: ['tests/fixtures/home.tsx'], bundle: true, write: false, platform: 'browser', format: 'iife',
    jsx: 'automatic', define: { 'process.env.NODE_ENV': '"production"', 'process.env': '{}' }, logLevel: 'silent',
    // The isolated fixture tests UI + API hooks, not Next routing or Clerk authentication.
    // Production routing/auth remain covered on the real /app route, without bypasses.
    plugins: [{ name: 'fixture-platform', setup(builder) {
      builder.onResolve({ filter: /^(next\/link|next\/navigation|@clerk\/nextjs)$/ }, args => ({ path: args.path, namespace: 'fixture-platform' }))
      builder.onLoad({ filter: /.*/, namespace: 'fixture-platform' }, args => ({ loader: 'tsx', resolveDir: process.cwd(), contents:
        args.path === 'next/link' ? `import {forwardRef} from 'react'; export default forwardRef(function Link({prefetch,replace,scroll,locale,...props},ref){return <a {...props} ref={ref}/>})`
          : args.path === 'next/navigation' ? `export function usePathname(){return '/app'}`
          : `export function ClerkProvider({children}){return children}; export function useAuth(){throw Error('Clerk is not used by the fixture')}; export const useSession=useAuth; export const useUser=useAuth;` }))
    } }] })
  bundle = result.outputFiles[0].text
})

async function openFixture(page: Page, query = '') {
  await page.clock.setFixedTime(new Date('2026-10-07T02:00:00Z'))
  await page.goto('/app')
  const styles = await page.locator('link[rel=stylesheet]').evaluateAll(nodes => nodes.map(node => (node as HTMLLinkElement).href))
  await page.route('**/__home_fixture__/bundle.js', route => route.fulfill({ contentType: 'application/javascript', body: bundle }))
  await page.route(url => url.pathname === '/__home_fixture__', route => route.fulfill({ contentType: 'text/html', body:
    `<!doctype html><html lang="en"><head><script>${initialUiScript}</script>${styles.map(href => `<link rel="stylesheet" href="${href}">`).join('')}</head><body><div id="fixture"></div><script src="/__home_fixture__/bundle.js"></script></body></html>` }))
  await page.goto(`/__home_fixture__${query}`)
}

type MockOptions = { summary?: object; fail?: string; empty?: boolean; delay?: number }
async function mockHome(page: Page, options: MockOptions = {}) {
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    if (options.delay) await new Promise(resolve => setTimeout(resolve, options.delay))
    if (url.pathname === options.fail) return route.fulfill({ status: 503, json: { error: 'not_ready' } })
    expect(route.request().headers().authorization).toBe('Bearer test-only-bearer')
    if (url.pathname.endsWith('/progress')) return route.fulfill({ json: options.summary ?? (options.empty ? { ...summary, total: 0, new: 0, studied: 0, due: 0, not_due: 0, reachable_decks: 0 } : summary) })
    if (url.pathname.endsWith('/activity')) {
      const start = url.searchParams.get('start_date')!, end = url.searchParams.get('end_date')!
      const days = []
      for (let day = start; day <= end; day = shiftDay(day, 1)) {
        const active = !options.empty && day >= '2026-10-01' && day !== '2026-10-07'
        days.push({ day, applied_events: active ? Number(day.slice(-2)) * 3 : 0, practice_events: active ? 2 : 0 })
      }
      return route.fulfill({ json: { as_of: summary.as_of, timezone: 'Asia/Ho_Chi_Minh', start_date: start, end_date: end, days,
        applied_events: days.reduce((sum, day) => sum + day.applied_events, 0), practice_events: days.reduce((sum, day) => sum + day.practice_events, 0), current_streak: options.empty ? 0 : 6, longest_streak: options.empty ? 0 : 12 } })
    }
    if (url.pathname.endsWith('/review-schedule')) {
      const start = url.searchParams.get('start_date')!, end = url.searchParams.get('end_date')!
      const days = Array.from({ length: 7 }, (_, index) => ({ day: shiftDay(start, index), count: options.empty ? 0 : [2, 8, 16, 0, 12, 6, 4][index] }))
      return route.fulfill({ json: { node_id: 'library-root', as_of: summary.as_of, timezone: 'Asia/Ho_Chi_Minh', start_date: start, end_date: end, days } })
    }
    if (url.pathname.endsWith('/nodes')) {
      const published = url.searchParams.get('parent_id') === 'published-root'
      const nodes = options.empty || published ? [] : ['Everyday conversation', 'Business English', 'Travel essentials'].map((name, index) => ({
        id: `node-${index}`, name, type: ['DECK', 'FOLDER', 'REFERENCE'][index], description: null, summary: { ...summary, node_id: `node-${index}`, total: 50, new: 20, studied: 30, due: 4, not_due: 26 },
      }))
      return route.fulfill({ json: { nodes, next_cursor: null } })
    }
    throw new Error(`Unexpected Home request: ${url}`)
  })
}

test('Home contracts reject missing counts, inconsistent totals and incomplete reporting windows', () => {
  expect(parseSummary(summary)).toMatchObject({ total: 142, due: 12 })
  for (const value of [{ ...summary, due: null }, { ...summary, total: 999 }, { ...summary, due: -1 }]) expect(() => parseSummary(value)).toThrow(HomeApiError)
  const value = { as_of: summary.as_of, timezone: 'UTC', start_date: '2026-10-01', end_date: '2026-10-02', current_streak: 0, longest_streak: 0, applied_events: 0, practice_events: 0,
    days: [{ day: '2026-10-01', applied_events: 0, practice_events: 0 }] }
  expect(() => parseActivity(value)).toThrow(HomeApiError)
  expect(() => parseActivity({ ...value, days: [...value.days, { day: '2026-10-02', applied_events: 0, practice_events: 0 }] })).not.toThrow()
  expect(() => parseSchedule({ ...value, node_id: 'root', days: [] })).toThrow(HomeApiError)
  expect(() => parseLibrary({ nodes: [], next_cursor: null })).not.toThrow()
  expect(() => parsePreparation({ node_id: 'root', selection: 'DUE', actual_sense_count: 0, actual_question_count: 3 })).toThrow(HomeApiError)
})

test('Home calendar respects reporting timezone, leap months and monotonic activity levels', () => {
  expect(reportingDay(new Date('2026-10-06T18:00:00Z'), 'Asia/Ho_Chi_Minh')).toBe('2026-10-07')
  expect(reportingDay(new Date('2026-10-06T18:00:00Z'), 'America/New_York')).toBe('2026-10-06')
  expect(shiftDay('2024-03-01', -1)).toBe('2024-02-29')
  expect(monthCells('2024-02-10').filter(Boolean)).toHaveLength(29)
  expect(monthCells('2026-10-07').filter(Boolean)).toHaveLength(31)
  expect(monthCells('2026-10-07').slice(0, 7)).toEqual([null, null, null, '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04'])
  expect(monthCells('2026-10-07')[7]).toBe('2026-10-05')
  expect([0, 1, 4, 5, 14, 15, 29, 30].map(activityLevel)).toEqual([0, 1, 1, 2, 2, 3, 3, 4])
})

test('Home requests use bearer authentication and tokens can be cancelled while loading', async () => {
  const original = globalThis.fetch
  let init: RequestInit | undefined
  globalThis.fetch = async (_url, options) => { init = options; return new Response(JSON.stringify(summary)) }
  try {
    expect((await homeRequest('study/progress', 'bearer', parseSummary, new AbortController().signal)).due).toBe(12)
    expect(init?.cache).toBe('no-store')
    expect(init?.headers).toEqual({ Authorization: 'Bearer bearer' })
    const controller = new AbortController()
    const waiting = homeToken(() => new Promise(() => {}), controller.signal)
    controller.abort(new Error('timed out'))
    await expect(waiting).rejects.toThrow('timed out')
    await expect(homeToken(async () => null, new AbortController().signal)).rejects.toMatchObject({ status: 401 })
  } finally { globalThis.fetch = original }
})

test('mock-mode Home reads the shared sample database without backend or Clerk requests', async ({ page }) => {
  const requests: string[] = []
  page.on('request', request => {
    const url = new URL(request.url())
    // Local JS chunks may contain the SDK's name; they are not Clerk-service requests.
    if (url.pathname.startsWith('/api/v1/') || url.origin !== new URL(test.info().project.use.baseURL!).origin) requests.push(request.url())
  })
  await page.goto('/app')
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening), Alex/ })).toBeVisible()
  await expect(page.locator('.home-count-due dd')).toHaveText('12')
  await expect(page.getByText('Design preview · Sample data · Nothing is saved to your account')).toBeVisible()
  await page.getByRole('button', { name: 'Start review', exact: true }).click()
  await expect(page.getByRole('region', { name: 'Start learning session' }).getByRole('link', { name: 'Start session' }))
    .toHaveAttribute('href', '/focus/learn?node=preview-library&selection=DUE')
  await page.getByRole('tab', { name: 'Published' }).click()
  await expect(page.getByRole('link', { name: /A few useful expressions/ })).toBeVisible()
  await expect(page.getByText('This page is a placeholder')).toHaveCount(0)
  expect(requests).toEqual([])
})

test('five Home regions show real contract data, scoped Library tabs and accessible calendar details', async ({ page }) => {
  await mockHome(page)
  await openFixture(page)
  for (const name of ['Today', 'Study streak', 'From your Library', 'Study activity', 'Upcoming reviews']) await expect(page.getByRole('region', { name, exact: true })).toBeVisible()
  await expect(page.locator('.home-count-due dd')).toHaveText('12')
  await expect(page.locator('.home-streak-number strong')).toHaveText('6')
  await expect(page.locator('.home-status-band')).toHaveAttribute('aria-label', /12 due, 46 new, 84 not yet due; 142 total/)
  await expect(page.getByText('Counted once, even across multiple decks.')).toHaveCount(0)
  await expect(page.getByText('Each accepted meaning result is one event.', { exact: false })).toHaveCount(0)
  await expect(page.getByText('Your current schedule, not a prediction.', { exact: false })).toHaveCount(0)
  await expect(page.locator('.home-page .home-footnote')).toHaveCount(0)
  await expect(page.locator('.home-activity-detail')).toHaveCount(0)
  await expect(page.locator('.home-calendar-day')).toHaveCount(31)
  await expect(page.getByRole('button', { name: /Thursday, Oct 1:/ })).toHaveText('1')
  await expect(page.getByRole('button', { name: /Wednesday, Oct 7:/ })).toHaveAttribute('aria-current', 'date')
  await expect(page.getByRole('link', { name: /Everyday conversation/ })).toHaveAttribute('href', '/app/personal/node-0')
  await page.getByRole('tab', { name: 'Published', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'Nothing published yet.' })).toBeVisible()
  await page.getByRole('tab', { name: 'Personal', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('link', { name: /Everyday conversation/ })).toBeVisible()
  const day = page.getByRole('button', { name: 'Tuesday, Oct 6: 20 learning events' })
  await day.focus()
  await expect(page.getByRole('tooltip')).toContainText('20 learning events')
  await page.keyboard.press('Enter')
  await expect(page.locator('.home-activity-detail')).toHaveText('Oct 6 · 18 scheduled results · 2 early practice results')
  await expect(page.getByRole('button', { name: /Oct 8: upcoming day/ })).toBeDisabled()
  await expect(page.locator('.home-schedule-list li')).toHaveCount(7)
})

test('Home starts Due-only focus mode without preparing or submitting on the Home page', async ({ page }) => {
  const posts: string[] = []
  page.on('request', request => { if (request.method() === 'POST') posts.push(new URL(request.url()).pathname) })
  await mockHome(page)
  await openFixture(page)
  await page.getByRole('button', { name: 'Start review', exact: true }).click()
  const panel = page.getByRole('region', { name: 'Start learning session' })
  await expect(panel.getByRole('link', { name: 'Start session' })).toHaveAttribute('href', '/focus/learn?node=library-root&selection=DUE')
  expect(posts).toEqual([])
  await page.getByRole('button', { name: 'Close session preparation' }).click()
  await expect(panel).toHaveCount(0)
})

test('empty Library, no Due and no activity have distinct honest states', async ({ page }) => {
  await mockHome(page, { empty: true })
  await openFixture(page)
  await expect(page.getByRole('heading', { name: 'Your Library starts here.' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Start review' })).toHaveCount(0)
  await expect(page.getByText('No activity recorded this month.', { exact: false })).toBeVisible()
  await expect(page.getByText('No future reviews scheduled in this window.')).toBeVisible()
  await page.unroute('**/api/v1/**')
  await mockHome(page, { summary: { ...summary, due: 0, not_due: 96 } })
  await page.getByRole('button', { name: 'Refresh Library counts' }).click()
  await expect(page.getByRole('button', { name: 'Learn new', exact: true })).toBeVisible()
  await expect(page.getByText('No reviews due right now.')).toBeVisible()
})

test('independent errors never masquerade as zero and recover without hiding other sections', async ({ page }) => {
  await mockHome(page, { fail: '/api/v1/study/progress' })
  await openFixture(page)
  const today = page.getByRole('region', { name: 'Today', exact: true })
  await expect(today.getByRole('alert')).toContainText('Could not load Library counts.')
  await expect(today.locator('dd')).toHaveCount(0)
  await expect(page.getByRole('link', { name: /Everyday conversation/ })).toBeVisible()
  await expect(page.locator('.home-streak-number strong')).toHaveText('6')
  await page.unroute('**/api/v1/**')
  await mockHome(page)
  await today.getByRole('button', { name: 'Retry', exact: true }).click()
  await expect(page.locator('.home-count-due dd')).toHaveText('12')
})

test('private Home data disappears synchronously on account change, including pending requests', async ({ page }) => {
  await mockHome(page, { delay: 200 })
  await openFixture(page)
  await expect(page.getByRole('status', { name: 'Loading Library counts' })).toBeVisible()
  await page.evaluate(() => window.dispatchEvent(new CustomEvent('test-account-change', { detail: null })))
  await expect(page.getByText('Signed out of the test fixture.')).toBeVisible()
  await expect(page.locator('.home-counts')).toHaveCount(0)
  await expect(page.locator('.home-library-list')).toHaveCount(0)
})

test('native and Radix scrollbars share rectangular themed rails', async ({ page }) => {
  await mockHome(page)
  await openFixture(page, '?scroll')
  const viewport = page.locator('[data-slot=scroll-area-viewport]')
  await viewport.hover()
  await expect(page.locator('[data-slot=scroll-area-thumb]')).toBeVisible()
  for (const dark of [false, true]) {
    await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
    await expect.poll(() => viewport.evaluate(node => getComputedStyle(node).colorScheme)).toBe(dark ? 'dark' : 'light')
    await page.waitForTimeout(200)
    const colors = await page.locator('[data-slot=scroll-area-thumb]').evaluate(node => {
      const baseProbe = document.createElement('span'), hoverProbe = document.createElement('span')
      baseProbe.style.backgroundColor = 'var(--scrollbar-thumb)'
      hoverProbe.style.backgroundColor = 'var(--scrollbar-thumb-hover)'
      document.body.append(baseProbe, hoverProbe)
      const base = getComputedStyle(baseProbe).backgroundColor, hover = getComputedStyle(hoverProbe).backgroundColor
      baseProbe.remove(); hoverProbe.remove()
      return { radius: getComputedStyle(node).borderRadius, thumb: getComputedStyle(node).backgroundColor, native: getComputedStyle(document.documentElement, '::-webkit-scrollbar-thumb').backgroundColor, base, hover }
    })
    expect(colors.radius).toBe('0px')
    expect([colors.base, colors.hover]).toContain(colors.thumb)
    // Chromium reports host hover when querying a native scrollbar pseudo-element.
    expect([colors.base, colors.hover]).toContain(colors.native)
    await viewport.evaluate(node => node.scrollTo({ top: 100 }))
    expect(await viewport.evaluate(node => node.scrollTop)).toBe(100)
  }
})

test('Home desktop/mobile theme matrix, keyboard contrast and long content remain in frame', async ({ page }) => {
  await mockHome(page)
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const directory = process.env.HOME_SCREENSHOT_DIR || '/tmp/opencode/pycil-home'
  mkdirSync(directory, { recursive: true })
  for (const width of [1440, 1280, 768, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 })
    await openFixture(page)
    await expect(page.locator('.home-count-due dd')).toHaveText('12')
    await expect(page.getByRole('link', { name: /Everyday conversation/ })).toBeVisible()
    for (const dark of [false, true]) {
      await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      const tile = await page.locator('.home-calendar-day').first().boundingBox()
      expect(tile!.width).toBeCloseTo(tile!.height, 1)
      expect(tile!.width).toBeGreaterThanOrEqual(24)
      const columns = await page.locator('.home-calendar').evaluate(node => getComputedStyle(node).gridTemplateColumns.split(' ').length)
      expect(columns).toBe(7)
      const thursday = await page.locator('.home-calendar-weekdays > span').nth(3).boundingBox()
      expect(tile!.x).toBeCloseTo(thursday!.x, 1)
      const monday = await page.getByRole('button', { name: /Monday, Oct 5:/ }).boundingBox()
      const mondayLabel = await page.locator('.home-calendar-weekdays > span').first().boundingBox()
      expect(monday!.x).toBeCloseTo(mondayLabel!.x, 1)
      expect(monday!.y).toBeGreaterThan(tile!.y)
      const ratios = await page.locator('.home-calendar-day').first().evaluate(node => {
        const canvas = document.createElement('canvas')
        canvas.width = canvas.height = 1
        const context = canvas.getContext('2d')!
        const luminance = (color: string) => {
          context.fillStyle = color; context.fillRect(0, 0, 1, 1)
          const channels = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map(value => {
            const channel = value / 255
            return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4
          })
          return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
        }
        const original = node.getAttribute('data-level')!
        const ratios = [0, 1, 2, 3, 4].map(level => {
          node.setAttribute('data-level', String(level))
          const style = getComputedStyle(node)
          const foreground = luminance(style.color), background = luminance(style.backgroundColor)
          return (Math.max(foreground, background) + .05) / (Math.min(foreground, background) + .05)
        })
        node.setAttribute('data-level', original)
        return ratios
      })
      for (const ratio of ratios) expect(ratio).toBeGreaterThanOrEqual(4.5)
      await page.getByRole('button', { name: 'Start review', exact: true }).focus()
      await expect(page.getByRole('button', { name: 'Start review', exact: true })).toBeFocused()
      await page.screenshot({ path: `${directory}/${width}-${dark ? 'dark' : 'light'}.png`, fullPage: true, animations: 'disabled' })
    }
  }
  expect(errors).toEqual([])
})
