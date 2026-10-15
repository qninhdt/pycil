import { createClerkClient } from '@clerk/backend'
import { test, expect } from '../../fixtures/index.ts'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { clerk } from '@clerk/testing/playwright'

import { signIn } from '../../fixtures/users.ts'

test('the custom sign-in form returns to the protected destination with the same account', async ({ user }) => {
  const { page } = user
  await clerk.signOut({ page })
  await signIn(page, user.email, user.password, '/app/personal')
  expect(await user.api.call<{ id: string }>('me')).toMatchObject({ id: user.account.id })
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Personal')
})

test('signing out and switching accounts clears the previous account library from the browser', async ({ user, secondary, data }) => {
  const deck = await data.create({ name: 'First account private finance', type: 'deck' })
  await user.page.goto('/app/personal')
  await expect(user.page.getByRole('link').filter({ hasText: deck.name })).toBeVisible()
  try {
    await user.page.getByRole('button', { name: 'Open account menu', exact: true }).click()
    await user.page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
    await expect(user.page).toHaveURL(/\/login$/)
    await signIn(user.page, secondary.email, secondary.password, '/app/personal')
    await expect(user.page.getByRole('heading', { level: 1 })).toContainText('Personal')
    await expect(user.page.getByRole('link').filter({ hasText: deck.name })).not.toBeVisible()
    expect(await user.api.call('me')).toMatchObject({ id: secondary.account.id })
    await user.page.reload()
    await expect(user.page.getByRole('link').filter({ hasText: deck.name })).not.toBeVisible()
  } finally {
    await clerk.signOut({ page: user.page })
    await signIn(user.page, user.email, user.password, '/app')
  }
})

for (const invalid of ['wrong_password', 'unknown_account']) {
  test(`invalid credentials (${invalid}) never create a protected session`, async ({ user, guest }) => {
    await setupClerkTestingToken({ page: guest })
    await guest.goto('/login?returnTo=%2Fapp')
    await guest.getByLabel('Email', { exact: true }).fill(invalid === 'wrong_password' ? user.email : `missing-${user.subject}+clerk_test@example.com`)
    await guest.getByLabel('Password', { exact: true }).fill('Incorrect-password!7')
    await guest.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(guest.getByRole('alert').filter({ hasText: 'The email or password is incorrect.' })).toBeVisible()
    await guest.goto('/app/personal')
    await expect(guest).toHaveURL(/\/login/)
  })
}

test('a refreshed token and a new tab preserve the same backend account', async ({ user }) => {
  const identity = await user.page.evaluate(async () => {
    const first = await window.Clerk.session?.getToken()
    const fresh = await window.Clerk.session?.getToken({ skipCache: true })
    return { firstPresent: Boolean(first), freshPresent: Boolean(fresh) }
  })
  expect(identity).toEqual({ firstPresent: true, freshPresent: true })
  const other = await user.page.context().newPage()
  try {
    await other.goto('/app/settings')
    await expect(other.getByRole('heading', { level: 1 })).toContainText('Settings')
    expect(await user.api.call('me')).toMatchObject({ id: user.account.id })
  } finally { await other.close() }
})

test('revoking the current Clerk session removes private content and offers sign-in recovery', async ({ user, data }) => {
  const deck = await data.create({ name: 'Revoked private collection', type: 'deck' })
  await user.page.goto(`/app/personal/${deck.id}`)
  await clerk.loaded({ page: user.page })
  await user.page.waitForFunction(() => Boolean(window.Clerk.session))
  const id = await user.page.evaluate(() => window.Clerk.session?.id)
  expect(id).toBeTruthy()
  await createClerkClient({ secretKey: process.env.CLERK_SECRET_KEY! }).sessions.revokeSession(id!)
  await user.page.reload()
  try {
    await expect(user.page.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible()
    await expect(user.page.getByRole('heading', { name: deck.name, exact: true })).not.toBeVisible()
    await user.page.getByRole('link', { name: 'Sign in', exact: true }).click()
    await expect(user.page).toHaveURL(/\/login\?returnTo=/)
  } finally {
    await signIn(user.page, user.email, user.password, '/app')
  }
})
