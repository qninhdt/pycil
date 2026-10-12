import { test, expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import { authErrorMessage, safeReturnTo } from '../src/lib/auth-flow'
import { fetchProfile, ApiError } from '../src/lib/api'
import { generateBauhausPattern } from '../src/lib/bauhaus-pattern'
import { createMockServices } from '../src/lib/services/mock'

test('post-auth destinations cannot leave the application subtree', () => {
  for (const value of ['https://evil.example', '//evil.example', '/app\\evil', '/application', '/login', '/app\n//evil']) expect(safeReturnTo(value)).toBe('/app')
  expect(safeReturnTo('/app/personal?create=deck')).toBe('/app/personal?create=deck')
  expect(authErrorMessage({ errors: [{ code: 'form_password_incorrect' }] })).toContain('email or password')
  expect(authErrorMessage({ errors: [{ code: 'form_identifier_not_found' }] })).toContain('email or password')
})

test('account adapter sends bearer tokens and distinguishes API failures', async () => {
  const original = globalThis.fetch
  let request: RequestInit | undefined
  globalThis.fetch = async (url, init) => {
    expect(url).toBe('/api/v1/me'); request = init
    return new Response(JSON.stringify({ ...createMockServices().account.initialProfile, id: 'account-1', display_name: 'Learner' }))
  }
  try {
    expect((await fetchProfile('session-token')).display_name).toBe('Learner')
    expect(request?.headers).toEqual({ Authorization: 'Bearer session-token' })
    expect(request?.cache).toBe('no-store')
    globalThis.fetch = async () => new Response(JSON.stringify({ error: 'invalid_credentials' }), { status: 401 })
    await expect(fetchProfile('expired')).rejects.toMatchObject({ status: 401, code: 'invalid_credentials' })
    globalThis.fetch = async () => new Response(JSON.stringify({ id: 'account-1', plan: 'invented' }))
    await expect(fetchProfile('session-token')).rejects.toBeInstanceOf(ApiError)
  } finally { globalThis.fetch = original }
})

test('app routes, deck creation dialog, account menu and theme persist', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let apiRequests = 0
  page.on('request', request => { if (request.url().includes('/api/v1/')) apiRequests++ })
  await page.goto('/app')
  await expect(page).toHaveURL(/\/app$/)
  await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening)(, Alex)?/ })).toBeVisible()
  await page.getByRole('link', { name: 'Dictionary', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/dictionary$/)
  await expect(page.getByRole('link', { name: 'Dictionary', exact: true })).toHaveAttribute('aria-current', 'page')
  await page.getByRole('button', { name: 'New deck / folder' }).click()
  await page.getByRole('menuitem', { name: 'New deck', exact: true }).click()
  await expect(page.getByRole('dialog', { name: 'New deck' })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('menuitem', { name: 'Settings' }).click()
  await expect(page).toHaveURL(/\/app\/settings$/)
  await page.getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('switch', { name: 'Dark mode' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.reload()
  await expect(page.locator('html')).toHaveClass(/dark/)
  expect(apiRequests).toBe(0)
  expect(errors).toEqual([])
})

test('page navigation starts at the top and history restores each visit in the workspace', async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 600 })
    await page.goto('/app')
    await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening)/ })).toBeVisible()
    await expect.poll(() => page.evaluate(() => window.history.state?.pycilWorkspaceEntry)).toBeTruthy()
    await expect(page.locator('#app-content [role="status"][aria-label^="Loading"]')).toHaveCount(0)
    await page.evaluate(() => document.fonts.ready)
    const workspace = page.locator('.shell-workspace')
    async function scroll(top: number) {
      await workspace.evaluate((element, top) => new Promise<void>(resolve => {
        element.addEventListener('scroll', () => resolve(), { once: true })
        element.scrollTop = top
      }), top)
      await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(top)
    }
    await scroll(400)
    async function navigate(name: 'Home' | 'Dictionary') {
      if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
      const nav = (width < 768 ? page.getByRole('dialog') : page.locator('.shell-desktop')).getByRole('navigation', { name: 'App navigation' })
      await nav.getByRole('link', { name, exact: true }).click()
    }
    async function settings() {
      if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
      await (width < 768 ? page.getByRole('dialog') : page.locator('.shell-desktop')).getByRole('button', { name: 'Open account menu' }).click()
      await page.getByRole('menuitem', { name: 'Settings', exact: true }).click()
      if (width < 768) await expect(page.getByRole('dialog', { name: 'Pycil navigation', exact: true })).toHaveCount(0)
      await expect(page).toHaveURL(/\/app\/settings$/)
      await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
    }
    await settings()
    await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(0)
    await scroll(100)
    await navigate('Home')
    await expect(page).toHaveURL(/\/app$/)
    await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(0)
    await scroll(200)
    for (const [direction, url, top] of [
      ['back', /\/app\/settings$/, 100], ['back', /\/app$/, 400],
      ['forward', /\/app\/settings$/, 100], ['forward', /\/app$/, 200],
    ] as const) {
      if (direction === 'back') await page.goBack()
      else await page.goForward()
      await expect(page).toHaveURL(url)
      await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(top)
    }
    await navigate('Dictionary')
    await expect(page).toHaveURL(/\/app\/dictionary$/)
    await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(0)
    await navigate('Home')
    await expect(page).toHaveURL(/\/app$/)
    await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(0)
  }
})

test('history restoration waits for content and stops when the user scrolls', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 600 })
  for (const cancel of [false, true]) {
    await page.goto('/app')
    await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening)/ })).toBeVisible()
    await expect(page.locator('#app-content [role="status"][aria-label^="Loading"]')).toHaveCount(0)
    const workspace = page.locator('.shell-workspace')
    await workspace.evaluate(element => new Promise<void>(resolve => {
      element.addEventListener('scroll', () => resolve(), { once: true })
      element.scrollTop = 400
    }))
    await page.getByRole('button', { name: 'Open account menu' }).click()
    await page.getByRole('menuitem', { name: 'Settings', exact: true }).click()
    await expect(page).toHaveURL(/\/app\/settings$/)
    await expect(page.getByRole('heading', { name: 'Settings', exact: true })).toBeVisible()
    // Keep content too short to restore, as it is while a route is loading.
    const loading = await page.addStyleTag({ content: '.shell-workspace main { display: none; }' })
    await page.goBack()
    await expect(page).toHaveURL(/\/app$/)
    await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(0)
    if (cancel) {
      await workspace.evaluate(element => {
        element.addEventListener('wheel', () => { element.setAttribute('data-wheel-received', 'true') }, { once: true })
      })
      await page.mouse.move(600, 300)
      await page.mouse.wheel(0, 100)
      await expect(workspace).toHaveAttribute('data-wheel-received', 'true')
    }
    await loading.evaluate(element => element.parentNode?.removeChild(element))
    await expect(page.getByRole('heading', { name: /Good (morning|afternoon|evening)/ })).toBeAttached()
    await expect.poll(() => workspace.evaluate(element => element.scrollTop)).toBe(cancel ? 0 : 400)
  }
})

test('navbar keeps its five primary items on Profile and Settings without a square strip', async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/u/alex')
    await expect(page.getByRole('heading', { name: 'Alex' })).toBeVisible()
    if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
    const scope = width < 768 ? page.getByRole('dialog') : page.locator('.shell-desktop')
    const nav = scope.getByRole('navigation', { name: 'App navigation' })
    await expect(nav.getByRole('link')).toHaveCount(5)
    await expect(nav.getByRole('separator')).toHaveCount(0)
    await expect(nav.locator('[data-dynamic], .shell-nav-rule')).toHaveCount(0)
    await expect(nav.locator('[aria-current=page]')).toHaveCount(0)
    await scope.getByRole('button', { name: 'Open account menu' }).click()
    await page.getByRole('menuitem', { name: 'Settings', exact: true }).click()
    await expect(page).toHaveURL(/\/app\/settings$/)
    if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
    await expect(nav.getByRole('link')).toHaveCount(5)
    await expect(nav.locator('[data-dynamic], .shell-nav-rule')).toHaveCount(0)
    await expect(page.locator('.shell-main-pattern')).toBeVisible()
    await nav.getByRole('link', { name: 'Home', exact: true }).click()
    if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
    await expect(nav.getByRole('link', { name: 'Home', exact: true })).toHaveAttribute('aria-current', 'page')
    for (const link of await nav.getByRole('link').all()) await expect(link).toHaveCSS('border-bottom-width', '1px')
    if (width >= 768) {
      await page.getByRole('button', { name: 'Collapse navigation' }).click()
      await expect.poll(() => scope.evaluate(node => node.getBoundingClientRect().width)).toBe(72)
      await expect(nav.getByRole('link')).toHaveCount(5)
      await expect(nav.getByRole('separator')).toHaveCount(0)
    }
  }
})

test('seeded patterns are deterministic, balanced and extend without changing existing blocks', () => {
  const blocks = generateBauhausPattern('pycil-1923')
  expect(generateBauhausPattern('pycil-1923')).toEqual(blocks)
  expect(generateBauhausPattern('another-seed')).not.toEqual(blocks)
  expect(generateBauhausPattern('pycil-1923', 12)).toEqual(blocks.slice(0, 12))
  expect(generateBauhausPattern('pycil-1923', 40).slice(0, 32)).toEqual(blocks)
  for (let color = 0; color < 4; color++) expect(blocks.filter(block => block.primary === color)).toHaveLength(8)
  for (const [index, block] of blocks.entries()) {
    expect(block.secondary).not.toBe(block.primary)
    expect([0, 90, 180, 270]).toContain(block.rotation)
    if (index) expect(block.motif).not.toBe(blocks[index - 1].motif)
  }
})

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
    await expect(preview.locator('.shell-nav-rule')).toHaveCount(0)
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

test('login validates and reveals password without fake authentication', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByRole('navigation', { name: 'App navigation' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByText('Enter your email address.', { exact: true })).toBeVisible()
  await expect(page.getByLabel('Email', { exact: true })).toBeFocused()
  await page.getByLabel('Email', { exact: true }).fill('learner@example.com')
  await page.getByLabel('Password', { exact: true }).fill('secret-for-test')
  await page.getByRole('button', { name: 'Show password', exact: true }).click()
  await expect(page.getByLabel('Password', { exact: true })).toHaveAttribute('type', 'text')
  await page.getByRole('button', { name: 'Hide password', exact: true }).click()
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.locator('.authentication-form').getByRole('alert')).toContainText('Sign-in is not configured')
  await expect(page).toHaveURL(/\/login$/)
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('secret-for-test')
})

test('collapsed navigation has one tooltip, compact logo, no horizontal scrolling and authored active icon', async ({ page }) => {
  await page.goto('/app')
  const nav = page.getByRole('navigation', { name: 'App navigation' })
  await expect(nav.locator('.shell-navigation-icon')).toHaveCount(5)
  await expect(nav.locator('.shell-navigation-icon[data-tone=mono]')).toHaveCount(1)
  await expect(nav.locator('.bauhaus-shape')).toHaveCount(0)
  await page.getByRole('button', { name: 'Collapse navigation' }).click()
  await expect(page.locator('.shell-brand-zone .pycil-logo')).toBeVisible()
  await expect(page.locator('.shell-brand-zone .pycil-wordmark')).toBeHidden()
  await page.mouse.move(500, 500)
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await nav.getByRole('link', { name: 'Dictionary', exact: true }).hover()
  await expect(page.getByRole('tooltip')).toHaveCount(1)
  await expect(page.getByRole('tooltip')).toHaveText('Dictionary')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  await nav.getByRole('link', { name: 'My Library', exact: true }).hover()
  await expect(page.getByRole('tooltip')).toHaveCount(1)
  await expect(page.getByRole('tooltip')).toHaveText('My Library')
  await nav.getByRole('link', { name: 'My Library', exact: true }).click()
  await page.mouse.move(500, 500)
  await expect(page.locator('.application-shell')).toHaveAttribute('data-collapsed', 'true')
  await expect(page.getByRole('tooltip')).toHaveCount(0)
  expect(await page.locator('.shell-rail-scroll').evaluate(e => e.scrollWidth <= e.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.getByRole('button', { name: 'Expand navigation' }).click()
  await expect(page.locator('.shell-brand-zone .pycil-wordmark')).toBeVisible()
  await expect.poll(() => page.locator('.shell-desktop').evaluate(e => e.getBoundingClientRect().width)).toBe(256)
  const corner = page.locator('.shell-new-corner')
  expect(await corner.locator('path').count()).toBe(1)
  const geometry = await corner.evaluate(e => { const r = e.getBoundingClientRect(); const p = e.parentElement!.getBoundingClientRect(); return { top: r.top - p.top, right: r.right - p.right, bottom: r.bottom - p.bottom } })
  expect(geometry.top).toBeGreaterThanOrEqual(0)
  expect(Math.abs(geometry.right)).toBeLessThanOrEqual(1)
  expect(geometry.bottom).toBeLessThanOrEqual(0)
})

test('brand uses vector lettering and shell reveal transitions have no stagger', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/app')
  const brand = page.locator('.shell-brand-zone .pycil-brand')
  await expect(brand.locator('svg')).toHaveCount(1)
  await expect(brand.locator('text, span')).toHaveCount(0)
  await expect(brand.locator('.pycil-wordmark path')).toHaveCount(6)
  await expect(brand.locator('.pycil-i-dot')).toHaveAttribute('fill', 'var(--art-red)')
  const transitions = await page.locator('.shell-desktop, .shell-workspace, .shell-brand-detail, .shell-new-corner, .shell-nav-label, .shell-brand-zone .pycil-wordmark').evaluateAll(nodes => nodes.map(node => {
    const style = getComputedStyle(node)
    return { delay: style.transitionDelay, duration: style.transitionDuration, animation: style.animationName }
  }))
  for (const transition of transitions) {
    expect(transition.delay).toBe('0s')
    expect(transition.duration).toBe('0.2s')
    expect(transition.animation).toBe('none')
  }
  await page.goto('/login')
  await expect(page.locator('.pycil-brand .pycil-wordmark path')).toHaveCount(6)
  await expect(page.locator('.pycil-brand text, .pycil-brand span')).toHaveCount(0)
})

test('collapse handle stays at account center and enlarged brand mark stays centered', async ({ page }) => {
  await page.goto('/app')
  for (const height of [1000, 450]) {
    await page.setViewportSize({ width: 1440, height })
    for (const collapsed of [false, true]) {
      if (collapsed) await page.getByRole('button', { name: 'Collapse navigation' }).click()
      await expect.poll(() => page.locator('.shell-desktop').evaluate(e => e.getBoundingClientRect().width)).toBe(collapsed ? 72 : 256)
      const geometry = await page.evaluate(() => {
        const handle = document.querySelector('.shell-collapse-handle')!.getBoundingClientRect()
        const account = document.querySelector('.shell-desktop .shell-account')!.getBoundingClientRect()
        const logo = document.querySelector('.shell-desktop .pycil-logo-full')!.getBoundingClientRect()
        return { centerDelta: handle.y + handle.height / 2 - account.y - account.height / 2, handleWidth: handle.width, handleHeight: handle.height, accountBottom: account.bottom, logoHeight: logo.height, documentWidth: document.documentElement.scrollWidth }
      })
      expect(geometry.centerDelta).toBe(0)
      expect(geometry.handleWidth).toBe(44)
      expect(geometry.handleHeight).toBe(44)
      expect(geometry.accountBottom).toBe(height)
      expect(geometry.logoHeight).toBe(32)
      expect(geometry.documentWidth).toBe(1440)
      if (collapsed) await page.getByRole('button', { name: 'Expand navigation' }).click()
    }
  }
})

test('mobile rail dropdowns open above their triggers without horizontal overflow', async ({ page }) => {
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 })
    await page.goto('/app')
    await page.getByRole('button', { name: 'Open navigation' }).click()
    const dialog = page.getByRole('dialog', { name: 'Pycil navigation' })
    await expect(dialog.locator('.shell-account > svg')).toHaveCount(1)
    for (const name of ['New deck / folder', 'Open account menu']) {
      const trigger = dialog.getByRole('button', { name, exact: true })
      await trigger.click()
      const menu = page.getByRole('menu')
      await expect(menu).toHaveAttribute('data-side', 'top')
      const bounds = await menu.boundingBox()
      expect(bounds!.x).toBeGreaterThanOrEqual(0)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.keyboard.press('Escape')
      await expect(menu).toBeHidden()
    }
  }
})

test('account dropdown shares New item spacing and separators meet the border on desktop and mobile', async ({ page }) => {
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/app')
    if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
    const scope = width < 768 ? page.getByRole('dialog') : page.locator('.shell-desktop')
    await scope.getByRole('button', { name: 'Open account menu' }).click()
    const menu = page.getByRole('menu')
    await expect.poll(() => menu.getByRole('menuitem').first().evaluate(item => item.getBoundingClientRect().height)).toBe(44)
    await expect(menu).toHaveCSS('animation-name', 'enter')
    const spacing = await menu.evaluate(node => {
      const label = node.querySelector<HTMLElement>('[data-slot=dropdown-menu-label]')!
      const items = [...node.querySelectorAll<HTMLElement>('[data-slot=dropdown-menu-item]')]
      const rect = node.getBoundingClientRect()
      const separators = [...node.querySelectorAll<HTMLElement>('[data-slot=dropdown-menu-separator]')].map(separator => ({ margin: getComputedStyle(separator).margin, left: separator.getBoundingClientRect().left - rect.left, right: rect.right - separator.getBoundingClientRect().right }))
      return { outer: getComputedStyle(node).padding, labelLeft: label.getBoundingClientRect().left + parseFloat(getComputedStyle(label).paddingLeft), separators, items: items.map(item => ({ height: item.getBoundingClientRect().height, contentLeft: item.getBoundingClientRect().left + parseFloat(getComputedStyle(item).paddingLeft), padding: getComputedStyle(item).padding, gap: getComputedStyle(item).gap })) }
    })
    expect(spacing.outer).toBe('0px')
    for (const item of spacing.items) {
      expect(item.height).toBe(44)
      expect(item.padding).toBe('8px 16px')
      expect(item.gap).toBe('12px')
      expect(item.contentLeft).toBe(spacing.labelLeft)
    }
    expect(spacing.separators).toHaveLength(2)
    for (const separator of spacing.separators) {
      expect(separator.margin).toBe('0px')
      expect(separator.left).toBe(1)
      expect(separator.right).toBe(1)
    }
    await page.keyboard.press('Escape')
    await scope.getByRole('button', { name: 'New deck / folder' }).click()
    const newSpacing = await page.getByRole('menu').getByRole('menuitem').first().evaluate(item => ({ padding: getComputedStyle(item).padding, gap: getComputedStyle(item).gap, minHeight: getComputedStyle(item).minHeight }))
    expect(newSpacing).toEqual({ padding: '8px 16px', gap: '12px', minHeight: '44px' })
    await expect(page.getByRole('menu').locator('small')).toHaveCount(0)
    await expect(page.getByRole('menuitem', { name: 'New deck', exact: true })).toBeVisible()
    await expect(page.getByRole('menuitem', { name: 'New folder', exact: true })).toBeVisible()
  }
})

test('dropdown hover and keyboard focus remain visible in both themes', async ({ page }) => {
  await page.goto('/app')
  for (const dark of [false, true]) {
    await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
    for (const [trigger, label] of [['Open account menu', 'Profile'], ['New deck / folder', 'New deck']]) {
      await page.getByRole('button', { name: trigger, exact: true }).click()
      const item = page.getByRole('menuitem', { name: label, exact: true })
      await item.hover()
      await expect(item).toHaveAttribute('data-highlighted', '')
      await expect(item).toBeFocused()
      const hover = await item.evaluate(node => {
        const style = getComputedStyle(node)
        const canvas = document.createElement('canvas')
        const context = canvas.getContext('2d')!
        const luminance = (color: string) => {
          context.fillStyle = style.getPropertyValue('--popover').trim()
          context.fillRect(0, 0, 1, 1)
          context.fillStyle = color
          context.fillRect(0, 0, 1, 1)
          const channels = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map(value => {
            const channel = value / 255
            return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4
          })
          return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722
        }
        const text = luminance(style.color)
        const background = luminance(style.backgroundColor)
        return { background: style.backgroundColor, contrast: (Math.max(text, background) + .05) / (Math.min(text, background) + .05) }
      })
      const surface = await page.getByRole('menu').evaluate(node => getComputedStyle(node).backgroundColor)
      expect(hover.background).not.toBe(surface)
      expect(hover.contrast).toBeGreaterThanOrEqual(4.5)
      await page.keyboard.press('ArrowDown')
      const next = page.getByRole('menu').locator('[data-highlighted]')
      await expect(next).toBeFocused()
      await expect(next).toHaveCSS('background-color', hover.background)
      await page.keyboard.press('Escape')
    }
  }
})

test('brand construction axes extend beyond the arc and rail dividers share the outer border color', async ({ page }) => {
  await page.clock.setFixedTime(new Date(2026, 9, 7, 9))
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 })
    await page.goto('/app')
    if (width < 768) await page.getByRole('button', { name: 'Open navigation' }).click()
    const scope = width < 768 ? page.getByRole('dialog') : page.locator('.shell-desktop')
    for (const dark of [false, true]) {
      await page.evaluate(dark => document.documentElement.classList.toggle('dark', dark), dark)
      await expect.poll(() => scope.evaluate(node => getComputedStyle(node.querySelector('.shell-brand-axes')!).stroke === getComputedStyle(node).borderRightColor)).toBe(true)
      const geometry = await scope.evaluate(node => {
        const arc = node.querySelector<SVGGraphicsElement>('.shell-brand-arc')!.getBBox()
        const axes = node.querySelector<SVGGraphicsElement>('.shell-brand-axes')!
        const bounds = axes.getBBox()
        const expected = getComputedStyle(node).borderRightColor
        const colors = [...node.querySelectorAll('.shell-brand-zone, .shell-nav > a, .shell-new')].map(element => getComputedStyle(element).borderBottomColor)
        return { arc: { width: arc.width, height: arc.height }, axes: { width: bounds.width, height: bounds.height }, stroke: getComputedStyle(axes).stroke, expected, colors }
      })
      expect(geometry.arc).toEqual({ width: 72, height: 72 })
      expect(geometry.axes).toEqual({ width: 96, height: 88 })
      expect(geometry.stroke).toBe(geometry.expected)
      for (const color of geometry.colors) expect(color).toBe(geometry.expected)
    }
  }
})

test('account popup clears the collapse hit area and the dark mode row and square switch keep it open', async ({ page }) => {
  await page.goto('/app')
  const switchButton = page.getByRole('switch', { name: 'Dark mode' })
  for (const collapsed of [false, true]) {
    if (collapsed) await page.getByRole('button', { name: 'Collapse navigation' }).click()
    await expect.poll(() => page.locator('.shell-desktop').evaluate(e => e.getBoundingClientRect().width)).toBe(collapsed ? 72 : 256)
    const trigger = page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })
    const handle = page.locator('.shell-collapse-handle')
    const triggerBounds = (await trigger.boundingBox())!
    const handleBounds = (await handle.boundingBox())!
    expect(triggerBounds.x + triggerBounds.width).toBeLessThanOrEqual(handleBounds.x)
    await trigger.focus()
    await trigger.press('Enter')
    const menu = page.getByRole('menu')
    await expect(menu).toHaveAttribute('data-side', 'right')
    await expect.poll(async () => (await menu.boundingBox())!.x - handleBounds.x - handleBounds.width).toBeGreaterThanOrEqual(12)
    await expect(switchButton).not.toBeChecked()
    await page.locator('.shell-theme-setting > span').first().click()
    await expect(switchButton).toBeChecked()
    await expect(menu).toBeVisible()
    await page.locator('.shell-theme-setting').click({ position: { x: 20, y: 22 } })
    await expect(switchButton).not.toBeChecked()
    const radius = await switchButton.evaluate(node => ({ track: getComputedStyle(node).borderRadius, thumb: getComputedStyle(node.querySelector('[data-slot=switch-thumb]')!).borderRadius }))
    expect(radius).toEqual({ track: '0px', thumb: '0px' })
    await switchButton.click()
    await expect(switchButton).toBeChecked()
    await expect(page.locator('html')).toHaveClass(/dark/)
    await expect(menu).toBeVisible()
    await switchButton.press('Space')
    await expect(switchButton).not.toBeChecked()
    await expect(page.locator('html')).not.toHaveClass(/dark/)
    await page.getByRole('menuitem', { name: 'Settings', exact: true }).focus()
    await page.keyboard.press('ArrowDown')
    await expect(page.getByRole('menuitemcheckbox', { name: 'Dark mode', exact: true })).toBeFocused()
    await page.keyboard.press('Enter')
    await expect(switchButton).toBeChecked()
    await expect(menu).toBeVisible()
    await page.keyboard.press('Space')
    await expect(switchButton).not.toBeChecked()
    await page.keyboard.press('Escape')
    await expect(trigger).toBeFocused()
  }
})

test('mobile theme switch stays in its popup', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 })
  await page.goto('/app')
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await page.getByRole('dialog').getByRole('button', { name: 'Open account menu' }).click()
  const themeSwitch = page.getByRole('switch', { name: 'Dark mode' })
  await themeSwitch.click()
  await expect(themeSwitch).toBeChecked()
  await expect(themeSwitch).toHaveCSS('border-radius', '0px')
  await expect(page.getByRole('menu')).toHaveAttribute('data-side', 'top')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  await page.keyboard.press('Escape')
  await page.keyboard.press('Escape')
})

test('account lettering stays on one line throughout sidebar expansion', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'no-preference' })
  await page.goto('/app')
  await page.getByRole('button', { name: 'Collapse navigation' }).click()
  await expect.poll(() => page.locator('.shell-desktop').evaluate(e => e.getBoundingClientRect().width)).toBe(72)
  const frames = await page.evaluate(async () => {
    const button = document.querySelector<HTMLButtonElement>('.shell-collapse-handle')!
    const title = document.querySelector<HTMLElement>('.account-copy strong')!
    const copy = title.parentElement!
    button.click()
    const samples = []
    for (let frame = 0; frame < 20; frame++) {
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
      samples.push({ height: title.getBoundingClientRect().height, width: copy.getBoundingClientRect().width, lineHeight: parseFloat(getComputedStyle(title).lineHeight) })
    }
    return samples
  })
  for (const frame of frames) {
    expect(frame.height).toBeCloseTo(frame.lineHeight, 0)
    expect(frame.width).toBe(147)
  }
})

test('signup requires matching passwords, recovery and callbacks are reachable', async ({ page }) => {
  await page.goto('/signup')
  await page.getByLabel('Email', { exact: true }).fill('learner@example.com')
  await page.getByLabel('Password', { exact: true }).fill('long-password')
  await page.getByLabel('Confirm password', { exact: true }).fill('different-password')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.getByText('The passwords do not match.', { exact: true })).toBeVisible()
  await page.getByLabel('Confirm password', { exact: true }).fill('long-password')
  await page.getByRole('button', { name: 'Create account', exact: true }).click()
  await expect(page.locator('.authentication-form').getByRole('alert')).toContainText('Sign-in is not configured')
  await page.getByRole('link', { name: 'Sign in', exact: true }).click()
  await page.getByRole('link', { name: 'Forgot password?' }).click()
  await expect(page.getByRole('heading', { name: 'Forgot your password?' })).toBeVisible()
  await page.getByRole('button', { name: 'Send reset code' }).click()
  await expect(page.getByText('Enter your email address.', { exact: true })).toBeVisible()
  await page.goto('/sso-callback')
  await expect(page.getByRole('heading', { name: 'Authentication is not configured.' })).toBeVisible()
})

test('mobile drawer navigates, closes and returns focus; small widths do not overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/app')
  const trigger = page.getByRole('button', { name: 'Open navigation' })
  await trigger.click()
  const dialog = page.getByRole('dialog', { name: 'Pycil navigation' })
  await expect(dialog).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(dialog).not.toBeVisible()
  await expect(trigger).toBeFocused()
  await trigger.click()
  await dialog.getByRole('link', { name: 'My Library', exact: true }).click()
  await expect(page).toHaveURL(/\/app\/personal\/preview-personal$/)
  await expect(dialog).not.toBeVisible()
  for (const width of [320, 768, 1200]) {
    await page.setViewportSize({ width, height: 900 })
    for (const route of ['/app/personal', '/login', '/signup']) {
      await page.goto(route)
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    }
  }
})

test('foundation desktop/mobile light/dark visual matrix', async ({ page }) => {
  const directory = process.env.FOUNDATION_SCREENSHOT_DIR || '.impeccable/review'
  mkdirSync(directory, { recursive: true })
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 })
    for (const theme of ['light', 'dark']) {
      await page.goto('/app')
      await page.evaluate(next => { localStorage.setItem('bauhaus-theme', next); document.documentElement.classList.toggle('dark', next === 'dark') }, theme)
      for (const [name, route] of [['shell', '/app'], ['login', '/login'], ['signup', '/signup']]) {
        await page.goto(route)
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
        await page.evaluate(() => document.fonts.ready)
        await page.screenshot({ path: `${directory}/${name}-${width}-${theme}.png`, fullPage: true, animations: 'disabled' })
        if (name === 'shell' && width === 1440) {
          await page.getByRole('button', { name: 'New deck / folder' }).click()
          await page.screenshot({ path: `${directory}/new-menu-${theme}.png`, fullPage: true, animations: 'disabled' })
          await page.keyboard.press('Escape')
          await page.getByRole('button', { name: 'Open account menu' }).click()
          await page.screenshot({ path: `${directory}/account-menu-${theme}.png`, fullPage: true, animations: 'disabled' })
          await page.keyboard.press('Escape')
          await page.getByRole('button', { name: 'Collapse navigation' }).click()
          await page.mouse.move(500, 500)
          await page.screenshot({ path: `${directory}/collapsed-${theme}.png`, fullPage: true, animations: 'disabled' })
          await page.getByRole('button', { name: 'Expand navigation' }).click()
        }
      }
    }
  }
})
