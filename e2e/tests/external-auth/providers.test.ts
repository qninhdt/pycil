import { authenticatorCode } from '../../support/authenticator.ts'
import { clerk, setupClerkTestingToken } from '@clerk/testing/playwright'
import { test, expect } from '../../fixtures/index.ts'


test('an enrolled authenticator is required by the real custom sign-in flow', async ({ actor }) => {
  if (process.env.E2E_TOTP_ENABLED !== 'true') throw new Error('External TOTP coverage requires E2E_TOTP_ENABLED=true and TOTP enabled in the Clerk development instance')
  const secret = await actor.page.evaluate(async () => (await window.Clerk.user!.createTOTP()).secret)
  if (!secret) throw new Error('Clerk did not return an enrollment secret')
  await actor.page.evaluate(async code => { await window.Clerk.user!.verifyTOTP({ code }) }, authenticatorCode(secret))
  await clerk.signOut({ page: actor.page })
  await setupClerkTestingToken({ page: actor.page })
  await actor.page.goto('/login')
  await actor.page.getByLabel('Email', { exact: true }).fill(actor.email)
  await actor.page.getByLabel('Password', { exact: true }).fill(actor.password)
  await actor.page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await expect(actor.page.getByLabel('Verification code', { exact: true })).toBeVisible()
  await actor.page.getByLabel('Verification code', { exact: true }).fill(authenticatorCode(secret))
  await actor.page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
  await expect(actor.page).toHaveURL(/\/app$/)
  expect(await actor.api.call('me')).toMatchObject({ id: actor.account.id })
})

test('Google OAuth returns through the application callback to an authenticated account', async ({ guest }) => {
  const email = process.env.E2E_GOOGLE_EMAIL
  const password = process.env.E2E_GOOGLE_PASSWORD
  if (!email || !password) throw new Error('External Google coverage requires dedicated E2E_GOOGLE_EMAIL and E2E_GOOGLE_PASSWORD credentials with Google OAuth enabled')
  await setupClerkTestingToken({ page: guest })
  await guest.goto('/login?returnTo=%2Fapp')
  await guest.getByRole('button', { name: /Google/ }).click()
  await expect(guest).toHaveURL(/accounts\.google\.com/)
  await guest.locator('input[type="email"]').fill(email)
  await guest.getByRole('button', { name: 'Next', exact: true }).click()
  await guest.locator('input[type="password"]').fill(password)
  await guest.getByRole('button', { name: 'Next', exact: true }).click()
  await expect(guest).toHaveURL(/localhost:3200\/app$/, { timeout: 60_000 })
  await expect(guest.getByRole('heading', { level: 1 })).toBeVisible()
})
