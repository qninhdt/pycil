import { expect,test } from './fixtures'
import { api } from './helpers/api'
import { signIn } from './helpers/auth'

import type { AccountProfile } from '../../src/lib/api'

test('settings persist languages and timezone, reject invalid drafts, and survive another session', async ({ page, browser, baseURL, profile }) => {
  try {
    await page.goto('/app/settings')
    await page.getByRole('combobox', { name: /^Time zone/ }).fill('not/a/timezone')
    await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toBeDisabled()
    await page.getByRole('combobox', { name: /^Time zone/ }).fill('Asia/Ho_Chi_Minh')
    await page.getByLabel(/Interface language/).selectOption('vi')
    await page.getByLabel(/Translation language/).selectOption('en')
    const saved = page.waitForResponse(r => r.url().endsWith('/me/settings') && r.request().method() === 'PATCH')
    await page.getByRole('button', { name: 'Save changes', exact: true }).click()
    expect((await saved).status()).toBe(200)
    await page.reload()
    await expect(page.getByRole('combobox', { name: /^Múi giờ/ })).toHaveValue('Asia/Ho_Chi_Minh')
    await expect(page.locator('html')).toHaveAttribute('lang', 'vi')
    const context = await browser.newContext({ baseURL })
    try {
      const other = await context.newPage()
      await signIn(other)
      await other.goto('/app/settings')
      await expect(other.getByRole('combobox', { name: /^Time zone/ })).toHaveValue('Asia/Ho_Chi_Minh')
      await expect(other.getByLabel(/Interface language/)).toHaveValue('vi')
      expect((await api<AccountProfile>(other, 'me')).body.settings).toMatchObject({ timezone: 'Asia/Ho_Chi_Minh', locale: 'vi', translation_language: 'en' })
    } finally { await context.close() }
  } finally { expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200) }
})

test('Free and Pro learning options enforce backend entitlement and keep failed drafts', async ({ page, browser, baseURL, profile }) => {
  expect(profile.plan).toBe('free')
  await page.goto('/app/settings')
  await page.getByRole('button', { name: 'Learning', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: /Single word/ })).toBeDisabled()
  expect((await api(page, 'me/settings', 'PATCH', { learning: { formats: ['single_word'] } })).status).toBe(403)
  const quantity = profile.settings.learning.questions_per_sense === 1 ? '2' : '1'
  await page.getByLabel(/Questions per sense/).fill(quantity)
  await page.route('**/v1/me/settings', route => route.abort('connectionfailed'))
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByText(/Could not|fetch/i).first()).toBeVisible()
  await expect(page.getByLabel(/Questions per sense/)).toHaveValue(quantity)
  await page.unroute('**/v1/me/settings')
  await page.getByRole('button', { name: 'Save changes', exact: true }).click()
  await expect(page.getByText('Settings saved', { exact: true })).toBeVisible()
  expect((await api(page, 'me/settings', 'PATCH', profile.settings)).status).toBe(200)
  const context = await browser.newContext({ baseURL })
  try {
    const other = await context.newPage()
    expect((await signIn(other, 'B')).plan).toBe('pro')
    await other.goto('/app/settings')
    await other.getByRole('button', { name: 'Learning', exact: true }).click()
    await expect(other.getByRole('checkbox', { name: /Single word/ })).toBeEnabled()
  } finally { await context.close() }
})
