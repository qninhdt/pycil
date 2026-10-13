import { test, expect } from '../../fixtures/index.ts'
import { clerk, setupClerkTestingToken } from '@clerk/testing/playwright'
import { randomUUID } from 'node:crypto'

test('reset rejects an invalid code and replaces the password used by the real sign-in form', async ({ actor }) => {
  const { page } = actor
  const password = `${randomUUID()}!aA7`
  await clerk.signOut({ page })
  await setupClerkTestingToken({ page })
  await page.goto('/forgot-password')
  await page.getByLabel('Email', { exact: true }).fill(actor.email)
  await page.getByRole('button', { name: 'Send reset code', exact: true }).click()
  await page.getByLabel('Verification code', { exact: true }).fill('123456')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: /code|incorrect|invalid/i })).toBeVisible()
  await page.getByLabel('Verification code', { exact: true }).fill('424242')
  await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await page.getByLabel('New password', { exact: true }).fill(password)
  await page.getByLabel('Confirm password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Reset password', exact: true }).click()
  await expect(page).toHaveURL(/\/app$/)
  expect(await actor.api.call('me')).toMatchObject({ id: actor.account.id })
  await clerk.signOut({ page })
  await page.goto('/login')
  await page.getByLabel('Email', { exact: true }).fill(actor.email)
  await page.getByLabel('Password', { exact: true }).fill(actor.password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(page.getByRole('alert').filter({ hasText: /password|incorrect|invalid/i })).toBeVisible()
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  const code = page.getByLabel('Verification code', { exact: true })
  await expect.poll(async () => new URL(page.url()).pathname === '/app' || await code.isVisible()).toBe(true)
  if (await code.isVisible()) {
    await code.fill('424242')
    await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  }
  await expect(page).toHaveURL(/\/app$/)
})
