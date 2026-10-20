import { test, expect } from '../../fixtures/index.ts'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { reserveIdentity, removeReservedIdentity } from '../../fixtures/users.ts'
import { Api } from '../../support/api.ts'

test('signup validates verification, resends the code and provisions one personal library', async ({ page }) => {
  const identity = await reserveIdentity()
  const api = await Api.create(page)
  try {
    await setupClerkTestingToken({ page })
    await page.goto('/signup?returnTo=%2Fapp%2Fpersonal')
    await page.getByLabel('Email', { exact: true }).fill(identity.email)
    await page.getByLabel('Password', { exact: true }).fill(identity.password)
    await page.getByLabel('Confirm password', { exact: true }).fill(identity.password)
    await page.getByRole('button', { name: 'Create account', exact: true }).click()
    await page.getByLabel('Verification code', { exact: true }).fill('123456')
    await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
    await expect(page.getByRole('alert').filter({ hasText: /code|incorrect|invalid/i })).toBeVisible()
    await page.getByRole('button', { name: 'Send a new code', exact: true }).click()
    await expect(page.getByRole('status').filter({ hasText: 'A new code has been sent.' })).toBeVisible()
    await page.getByLabel('Verification code', { exact: true }).fill('424242')
    await page.getByRole('button', { name: 'Verify and continue', exact: true }).click()
    await expect(page).toHaveURL(/\/app\/personal$/)
    const profile = await api.call<{ id: string; personal_node_id: string; published_node_id: string }>('me')
    await page.reload()
    expect(await api.call('me')).toMatchObject(profile)
    expect(profile.personal_node_id).not.toBe(profile.published_node_id)
  } finally {
    await api.dispose()
    await page.context().close()
    await removeReservedIdentity(identity.email)
  }
})
