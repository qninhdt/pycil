import { expect,test } from '@playwright/test'

import { navigationCollapsedKey } from '../../../src/lib/preferences/browser'

test('pattern resizes its block count without clipping and keeps its seed across resize and reload', async ({ page }) => {
  await page.goto('/app')
  const panel = page.locator('.shell-main-pattern')
  let original = ''
  for (const width of [1440, 1024, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 844 })
    await expect.poll(() => panel.evaluate(node => node.clientWidth)).toBe(width - (width >= 768 ? 256 : 0))
    await expect.poll(() => panel.locator('.fit-tile:visible').count()).toBe(Math.max(1, Math.round((width - (width >= 768 ? 256 : 0)) / 32)))
    const geometry = await panel.evaluate(node => {
      const blocks = [...node.querySelectorAll('.fit-tile')].filter(tile => getComputedStyle(tile).display !== 'none')
      const bounds = node.getBoundingClientRect()
      const first = blocks[0].getBoundingClientRect()
      const last = blocks.at(-1)!.getBoundingClientRect()
      return { left: first.left, right: last.right, bottom: last.bottom, expectedLeft: bounds.left, expectedRight: bounds.right, expectedBottom: bounds.bottom, first: blocks.slice(0, 4).map(block => block.outerHTML).join('') }
    })
    expect(geometry.left).toBeCloseTo(geometry.expectedLeft, 1)
    expect(geometry.right).toBeCloseTo(geometry.expectedRight, 1)
    expect(geometry.bottom).toBeCloseTo(geometry.expectedBottom, 1)
    if (!original) original = geometry.first
    expect(geometry.first).toBe(original)
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  const markup = await panel.locator('.fit-tile-grid').innerHTML()
  await page.reload()
  await expect.poll(() => panel.locator('.fit-tile-grid').innerHTML()).toBe(markup)
})

test('main pattern renders complete responsive tiles before hydration without JavaScript', async ({ browser, page }) => {
  const unhydrated = await browser.newContext({ javaScriptEnabled: false, baseURL: test.info().project.use.baseURL, viewport: { width: 1440, height: 844 } })
  try {
    const preview = await unhydrated.newPage()
    await preview.goto('/app')
    await expect(preview.locator('.shell-main-pattern')).toHaveCSS('height', '32px')
    await expect(preview.locator('.shell-main-pattern .fit-tile:visible')).toHaveCount(37)
    for (const width of [1024, 390, 768, 1440]) {
      await preview.setViewportSize({ width, height: 844 })
      const contentWidth = width - (width >= 768 ? 256 : 0)
      await expect.poll(() => preview.locator('.shell-main-pattern').evaluate(node => node.clientWidth)).toBe(contentWidth)
      await expect(preview.locator('.shell-main-pattern .fit-tile:visible')).toHaveCount(Math.round(contentWidth / 32))
    }
  } finally {
    await unhydrated.close()
  }
  for (let reload = 0; reload < 3; reload++) {
    if (reload) await page.reload()
    else await page.goto('/app')
    const pattern = page.locator('.shell-main-pattern')
    await expect(pattern.locator('svg:visible').first()).toBeVisible()
    await expect.poll(() => pattern.locator('.fit-tile:visible').count()).toBeGreaterThan(1)
  }
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
    await expect(page.getByRole('button', { name: 'Collapse navigation' })).toBeDisabled()
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

test('all 16 backgrounds re-anchor to wide, square and tall widgets, without clipping or distorting shapes', async ({ page }) => {
  await page.goto('/showcase')
  await page.getByRole('navigation', { name: 'Catalog categories' }).getByRole('button', { name: 'Artwork', exact: true }).click()
  const backgrounds = page.locator('#backgrounds svg.bauhaus-background')
  await expect(backgrounds).toHaveCount(16)
  for (const [width, height] of [[1000, 200], [400, 240], [360, 600], [400, 400]]) {
    await backgrounds.evaluateAll((nodes, size) => nodes.forEach(node => {
      const parent = node.parentElement!
      parent.style.width = `${size.width}px`
      parent.style.height = `${size.height}px`
      parent.style.flex = 'none'
    }), { width, height })
    await expect(async () => {
      const checks = await backgrounds.evaluateAll(nodes => nodes.map(node => {
        const svg = node as SVGSVGElement, bounds = svg.getBoundingClientRect(), canvas = svg.querySelector('[data-background-canvas]')!.getBoundingClientRect()
        const shapes = [...svg.querySelectorAll<SVGGraphicsElement>('path, circle, rect')].filter(shape => !shape.hasAttribute('data-background-canvas'))
        return {
          name: svg.dataset.background,
          ratioMatches: Math.abs(bounds.width / bounds.height - svg.viewBox.baseVal.width / svg.viewBox.baseVal.height) < .0001,
          canvasFills: Math.abs(canvas.width - bounds.width) <= 1.5 && Math.abs(canvas.height - bounds.height) <= 1.5,
          uniform: shapes.every(shape => { const matrix = shape.getScreenCTM()!; return Math.abs(matrix.a - matrix.d) < .0001 && matrix.b === 0 && matrix.c === 0 }),
          inside: shapes.every(shape => { const rect = shape.getBoundingClientRect(); return rect.left >= bounds.left - .5 && rect.right <= bounds.right + .5 && rect.top >= bounds.top - .5 && rect.bottom <= bounds.bottom + .5 }),
        }
      }))
      for (const check of checks) expect(check, `${check.name} at ${width}×${height}`).toMatchObject({ ratioMatches: true, canvasFills: true, uniform: true, inside: true })
    }).toPass()
  }
  const inverse = page.locator('#backgrounds [data-background=inverse-poster] [data-background-canvas]')
  await page.evaluate(() => document.documentElement.classList.remove('dark'))
  const light = await inverse.evaluate(node => getComputedStyle(node).fill)
  expect(light).toBe(await page.locator('body').evaluate(node => getComputedStyle(node).backgroundColor))
  await page.evaluate(() => document.documentElement.classList.add('dark'))
  await expect.poll(() => inverse.evaluate(node => getComputedStyle(node).fill)).not.toBe(light)
  const dark = await inverse.evaluate(node => getComputedStyle(node).fill)
  expect(dark).toBe(await page.locator('body').evaluate(node => getComputedStyle(node).backgroundColor))
  expect(dark).not.toBe(light)
})
