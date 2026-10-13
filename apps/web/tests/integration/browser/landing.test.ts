import { expect,test } from '@playwright/test'



test('the landing example connects meanings, decks and practice without saving progress', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  const writes: string[] = []
  page.on('request', request => { if (request.url().includes('/v1/') && request.method() !== 'GET') writes.push(request.url()) })
  await page.goto('/')
  await expect(page).toHaveURL(/\/$/)
  await expect(page).toHaveTitle('Pycil — A word is only the beginning')
  await expect(page.getByRole('heading', { level: 1 })).toHaveText('A word is onlythe beginning.')
  await expect(page.getByText('Interactive example · nothing is saved')).toBeVisible()
  await page.getByRole('button', { name: 'branch', exact: true }).click()
  await expect(page.locator('#learning-map').getByRole('status')).toContainText('Have another go.')
  await page.getByRole('button', { name: 'bank', exact: true }).click()
  await expect(page.locator('#learning-map').getByRole('status')).toContainText("That's it. We sat on the bank")
  const money = page.getByRole('button', { name: 'A place that keeps your money.', exact: true })
  await money.focus()
  await money.press('Enter')
  await expect(money).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByText('Everyday money', { exact: true })).toBeVisible()
  await expect(page.getByText('She went to the ___ to open an account.', { exact: true })).toBeVisible()
  await expect(page.locator('#learning-map').getByRole('status')).toHaveText('Choose the word that fits.')
  const bank = page.getByRole('button', { name: 'bank', exact: true })
  await bank.focus()
  await bank.press('Space')
  await expect(page.locator('#learning-map').getByRole('status')).toContainText("That's it. She went to the bank")
  await page.getByRole('button', { name: 'The land beside a river.', exact: true }).click()
  await expect(page.getByText('Along the river', { exact: true })).toBeVisible()
  await expect(page.getByText('We sat on the ___ and watched the water.', { exact: true })).toBeVisible()
  await expect(bank).toHaveAttribute('aria-pressed', 'false')
  expect(writes).toEqual([])
  expect(errors).toEqual([])
})

test('landing actions lead to the existing signup, login and application routes', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Build your vocabulary' }).click()
  await expect(page).toHaveURL(/\/signup$/)
  await expect(page.getByLabel('Email', { exact: true })).toBeVisible()
  await page.goto('/')
  await page.getByRole('link', { name: 'Sign in', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await page.goto('/')
  await page.getByRole('link', { name: 'Open the app', exact: true }).click()
  await expect(page).toHaveURL(/\/app$/)
})

test('the landing worksheet works at mobile, tablet and desktop widths in both themes', async ({ page }) => {
  for (const theme of ['light', 'dark']) {
    await page.goto('/')
    await page.evaluate(value => localStorage.setItem('bauhaus-theme', value), theme)
    for (const width of [320, 390, 768, 1024, 1280, 1440]) {
      await page.setViewportSize({ width, height: width >= 1280 ? 1000 : 844 })
      await page.goto('/')
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
      await expect(page.getByRole('link', { name: 'Get started' })).toBeVisible()
      const contrast = await page.locator('#landing-title span').evaluate(node => {
        const parseColor = (color: string) => {
          const values = color.match(/\d*\.?\d+/g)!.map(Number)
          return { rgb: values.slice(0, 3).map(value => value / (color.startsWith('color(srgb') ? 1 : 255)), alpha: values[3] ?? 1 }
        }
        const luminance = (color: string) => {
          const value = parseColor(color)
          const canvas = parseColor(getComputedStyle(document.body).backgroundColor).rgb
          const channels = value.rgb.map((channel, index) => channel * value.alpha + canvas[index] * (1 - value.alpha))
          return channels.map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
            .reduce((total, value, index) => total + value * [.2126, .7152, .0722][index], 0)
        }
        const ratio = (ink: string, paper: string) => {
          const values = [luminance(ink), luminance(paper)]
          return (Math.max(...values) + .05) / (Math.min(...values) + .05)
        }
        const deck = document.querySelector('#deck-title')!.closest('section')!
        return {
          heading: ratio(getComputedStyle(node).color, getComputedStyle(document.body).backgroundColor),
          deck: ratio(getComputedStyle(deck.querySelector('header span')!).color, getComputedStyle(deck).backgroundColor),
        }
      })
      expect(contrast.heading).toBeGreaterThanOrEqual(3)
      expect(contrast.deck).toBeGreaterThanOrEqual(4.5)
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.getByRole('button', { name: 'A place that keeps your money.', exact: true }).click()
      await expect(page.getByText('Everyday money', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: 'The land beside a river.', exact: true }).click()

    }
  }
})
