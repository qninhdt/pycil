import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { expect,type Page } from '@playwright/test'
import type { AccountProfile } from '../../../src/lib/api'
import { api } from './api'

export async function signIn(page: Page, account: 'A' | 'B' | 'C' = 'A', loginPath = '/login') {
  const email = process.env[`E2E_EMAIL_${account}`], password = process.env[`E2E_PASSWORD_${account}`]
  if (!email || !password) throw new Error(`Set E2E_EMAIL_${account} and E2E_PASSWORD_${account} for a dedicated Clerk test identity.`)
  await setupClerkTestingToken({ page })
  await page.goto(loginPath)
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeEnabled()
  await page.getByLabel('Email', { exact: true }).fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await expect(page.getByLabel('Email', { exact: true })).toHaveValue(email)
  await expect(page.getByLabel('Password', { exact: true })).toHaveValue(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await verifyDevice(page)
  const profile = await api<AccountProfile>(page, 'me')
  expect(profile.status).toBe(200)
  return profile.body
}

export async function signOut(page: Page) {
  await page.goto('/app')
  await api<AccountProfile>(page, 'me')
  await expect(page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' })).toContainText(/Free plan|Pro plan/)
  await page.locator('.shell-desktop').getByRole('button', { name: 'Open account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('button', { name: 'Sign in', exact: true })).toBeEnabled()
}

export async function verifyDevice(page: Page) {
  const code = page.getByLabel('Verification code', { exact: true })
  await expect.poll(async () => /\/app(?:\/|\?|$)/.test(new URL(page.url()).pathname) || await code.isVisible()).toBe(true)
  if (await code.isVisible()) {
    await code.fill('424242')
    await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  }
  await expect(page).toHaveURL(/\/app(?:\/|\?|$)/)
}
