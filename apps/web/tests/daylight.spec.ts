import { test, expect } from '@playwright/test'
import { getTimeOfDay, getNextTimeOfDayChange } from '../src/lib/time-of-day'
import { navigationCollapsedKey } from '../src/lib/ui-preferences'

test('day periods and their next boundaries use local calendar time', () => {
  for (const [hour, minute, period] of [[0, 0, 'night'], [4, 59, 'night'], [5, 0, 'morning'], [11, 59, 'morning'], [12, 0, 'afternoon'], [17, 59, 'afternoon'], [18, 0, 'night'], [23, 59, 'night']] as const) {
    const date = new Date(2026, 9, 7, hour, minute)
    expect(getTimeOfDay(date)).toBe(period)
    const next = getNextTimeOfDayChange(date)
    expect(next.getTime()).toBeGreaterThan(date.getTime())
    expect([5, 12, 18]).toContain(next.getHours())
    expect(next.getMinutes()).toBe(0)
    expect(getTimeOfDay(next)).not.toBe(period)
  }
  expect(getNextTimeOfDayChange(new Date(2026, 9, 7, 18))).toEqual(new Date(2026, 9, 8, 5))
})

test.describe('local-time artwork', () => {
  test.use({ timezoneId: 'Asia/Ho_Chi_Minh' })

  test('morning, afternoon and night have their own shape and axes in both themes and rails', async ({ page }) => {
    const states = [
      { date: '2026-10-07T02:00:00Z', period: 'morning', shape: '.shell-brand-arc', fill: 'rgb(231, 76, 60)', axes: 'M0 70.5h96M84.5 0v88' },
      { date: '2026-10-07T06:00:00Z', period: 'afternoon', shape: '.shell-brand-disc', fill: 'rgb(241, 196, 15)', axes: 'M0 44.5h96M60.5 0v88' },
      { date: '2026-10-07T13:00:00Z', period: 'night', shape: '.shell-brand-crescent', fill: 'rgb(52, 152, 219)', axes: 'M0 72.5h96M24.5 0v88' },
    ]
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 844 })
      for (const state of states) {
        await page.clock.setFixedTime(new Date(state.date))
        await page.goto('/app')
        if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
        const scope = width < 768 ? page.getByRole('dialog') : page.locator('.shell-desktop')
        const art = scope.locator('.shell-brand-detail')
        await expect(page.locator('html')).toHaveAttribute('data-time-of-day', state.period)
        await expect(art).toHaveAttribute('data-time-of-day', state.period)
        await expect(art.locator('.shell-brand-period:visible')).toHaveCount(1)
        for (const dark of [false, true]) {
          await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
          await expect(art.locator(state.shape)).toHaveCSS('fill', state.fill)
          await expect(art.locator('.shell-brand-axes:visible')).toHaveAttribute('d', state.axes)
          await expect.poll(() => art.locator('.shell-brand-axes:visible').evaluate(node => getComputedStyle(node).stroke === getComputedStyle(document.documentElement).getPropertyValue('--foreground').trim() || getComputedStyle(node).stroke === getComputedStyle(node.closest('.shell-brand-zone')!).borderBottomColor)).toBe(true)
        }
      }
    }
  })

  test('time hook updates at noon, night and dawn without reloading', async ({ page }) => {
    await page.clock.install({ time: new Date('2026-10-07T04:58:00Z') })
    await page.goto('/app')
    // Interact once to ensure hydration and the clock subscription are running.
    await page.getByRole('button', { name: 'Collapse navigation' }).click()
    await page.getByRole('button', { name: 'Expand navigation' }).click()
    await page.clock.pauseAt(new Date('2026-10-07T04:59:58Z'))
    const art = page.locator('.shell-desktop .shell-brand-detail')
    await expect(art).toHaveAttribute('data-time-of-day', 'morning')
    await page.clock.fastForward(2000)
    await expect(art).toHaveAttribute('data-time-of-day', 'afternoon')
    await page.clock.fastForward('06:00:00')
    await expect(art).toHaveAttribute('data-time-of-day', 'night')
    await page.clock.fastForward('11:00:00')
    await expect(art).toHaveAttribute('data-time-of-day', 'morning')
  })

  test('time and collapsed geometry are correct even before hydration', async ({ page }) => {
    await page.clock.setFixedTime(new Date('2026-10-07T13:00:00Z'))
    await page.addInitScript(key => localStorage.setItem(key, 'true'), navigationCollapsedKey)
    await page.route(url => url.pathname.endsWith('.js'), route => route.abort())
    await page.goto('/app', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('html')).toHaveAttribute('data-time-of-day', 'night')
    await expect(page.locator('html')).toHaveAttribute('data-navigation-collapsed', 'true')
    await expect(page.locator('.shell-desktop')).toHaveCSS('width', '72px')
    await expect(page.locator('.shell-workspace')).toHaveCSS('margin-left', '72px')
    await expect(page.locator('.shell-desktop .shell-brand-detail')).toHaveCSS('opacity', '0')
    await expect(page.locator('.shell-desktop .shell-nav-label').first()).toHaveCSS('visibility', 'hidden')
    await expect(page.locator('.shell-expand-arrow')).toHaveCSS('display', 'inline')
    await expect(page.locator('.shell-brand-period[data-period=night]')).toHaveCSS('display', 'inline')
    await expect(page.locator('.shell-brand-period[data-period=morning]')).toHaveCSS('display', 'none')
  })
})

test('navigation collapse persists through reload, routes and a second tab', async ({ page, context }) => {
  await page.goto('/app')
  await page.getByRole('button', { name: 'Collapse navigation' }).click()
  expect(await page.evaluate(key => localStorage.getItem(key), navigationCollapsedKey)).toBe('true')
  await page.reload()
  await expect(page.getByRole('button', { name: 'Expand navigation' })).toBeVisible()
  await expect(page.locator('.shell-desktop')).toHaveCSS('width', '72px')
  await page.goto('/app/settings')
  await expect(page.getByRole('button', { name: 'Expand navigation' })).toBeVisible()
  const second = await context.newPage()
  try {
    await second.goto('/app')
    await expect(second.getByRole('button', { name: 'Expand navigation' })).toBeVisible()
    await second.getByRole('button', { name: 'Expand navigation' }).click()
    await expect(page.getByRole('button', { name: 'Collapse navigation' })).toBeVisible()
    await expect.poll(() => page.locator('.shell-desktop').evaluate(node => node.getBoundingClientRect().width)).toBe(256)
    expect(await page.evaluate(key => localStorage.getItem(key), navigationCollapsedKey)).toBe('false')
  } finally { await second.close() }
  await page.reload()
  await expect(page.getByRole('button', { name: 'Collapse navigation' })).toBeVisible()
})

test('desktop collapse preference does not collapse the mobile drawer', async ({ page }) => {
  await page.addInitScript(key => localStorage.setItem(key, 'true'), navigationCollapsedKey)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/app')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  const drawer = page.getByRole('dialog')
  await expect(drawer.getByRole('link', { name: 'Dictionary', exact: true }).locator('.shell-nav-label')).toHaveCSS('visibility', 'visible')
  await expect(drawer.locator('.shell-brand-detail')).toHaveCSS('opacity', '1')
  await expect(drawer.getByRole('button', { name: 'Expand navigation' })).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})

test('storage failures do not break the clock or collapse control', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Storage blocked', 'SecurityError') } })
  })
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/app')
  await page.getByRole('button', { name: 'Collapse navigation' }).click()
  await expect(page.getByRole('button', { name: 'Expand navigation' })).toBeVisible()
  await page.getByRole('button', { name: 'Expand navigation' }).click()
  await expect(page.getByRole('button', { name: 'Collapse navigation' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('data-time-of-day', /morning|afternoon|night/)
  expect(errors).toEqual([])
})
