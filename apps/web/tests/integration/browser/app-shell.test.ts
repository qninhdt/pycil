import { expect,test } from '@playwright/test'


test('app routes, deck creation dialog, account menu and theme persist', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  let apiRequests = 0
  page.on('request', request => { if (request.url().includes('/v1/')) apiRequests++ })
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
    await expect(menu).toBeVisible()
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
    await expect(page.getByRole('menu')).toBeVisible()
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
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 })
    for (const theme of ['light', 'dark']) {
      await page.goto('/app')
      await page.evaluate(next => { document.cookie = `pycil-theme=${next}; Path=/; SameSite=Lax`; document.documentElement.classList.toggle('dark', next === 'dark') }, theme)
      for (const [name, route] of [['shell', '/app'], ['login', '/login'], ['signup', '/signup']]) {
        await page.goto(route)
        await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
        await page.evaluate(() => document.fonts.ready)
        if (name === 'shell' && width === 1440) {
          await page.getByRole('button', { name: 'New deck / folder' }).click()
          await page.keyboard.press('Escape')
          await page.getByRole('button', { name: 'Open account menu' }).click()
          await page.keyboard.press('Escape')
          await page.getByRole('button', { name: 'Collapse navigation' }).click()
          await page.mouse.move(500, 500)
          await page.getByRole('button', { name: 'Expand navigation' }).click()
        }
      }
    }
  }
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
