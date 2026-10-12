import { expect,test } from '@playwright/test'

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
