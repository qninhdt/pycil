import { createClerkClient } from '@clerk/backend'
import { test, expect } from '../../fixtures/index.ts'
import { setupClerkTestingToken } from '@clerk/testing/playwright'
import { clerk } from '@clerk/testing/playwright'

import { signIn } from '../../fixtures/actors.ts'

test('the custom sign-in form returns to the protected destination with the same account', async ({ actor }) => {
  const { page } = actor
  await clerk.signOut({ page })
  await signIn(page, actor.email, actor.password, '/app/personal')
  expect(await actor.api.call<{ id: string }>('me')).toMatchObject({ id: actor.account.id })
  await page.reload()
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Personal')
})

test('signing out and switching accounts clears the previous account library from the browser', async ({ actor, secondary, data }) => {
  const deck = await data.create({ name: 'First account private finance', type: 'deck' })
  await actor.page.goto('/app/personal')
  await expect(actor.page.getByRole('link').filter({ hasText: deck.name })).toBeVisible()
  try {
    await actor.page.getByRole('button', { name: 'Open account menu', exact: true }).click()
    await actor.page.getByRole('menuitem', { name: 'Sign out', exact: true }).click()
    await expect(actor.page).toHaveURL(/\/login$/)
    await signIn(actor.page, secondary.email, secondary.password, '/app/personal')
    await expect(actor.page.getByRole('heading', { level: 1 })).toContainText('Personal')
    await expect(actor.page.getByRole('link').filter({ hasText: deck.name })).not.toBeVisible()
    expect(await actor.api.call('me')).toMatchObject({ id: secondary.account.id })
    await actor.page.reload()
    await expect(actor.page.getByRole('link').filter({ hasText: deck.name })).not.toBeVisible()
  } finally {
    await clerk.signOut({ page: actor.page })
    await signIn(actor.page, actor.email, actor.password, '/app')
  }
})

for (const invalid of ['wrong_password', 'unknown_account']) {
  test(`invalid credentials (${invalid}) never create a protected session`, async ({ actor, guest }) => {
    await setupClerkTestingToken({ page: guest })
    await guest.goto('/login?returnTo=%2Fapp')
    await guest.getByLabel('Email', { exact: true }).fill(invalid === 'wrong_password' ? actor.email : `missing-${actor.subject}+clerk_test@example.com`)
    await guest.getByLabel('Password', { exact: true }).fill('Incorrect-password!7')
    await guest.getByRole('button', { name: 'Sign in', exact: true }).click()
    await expect(guest.getByRole('alert').filter({ hasText: 'The email or password is incorrect.' })).toBeVisible()
    await guest.goto('/app/personal')
    await expect(guest).toHaveURL(/\/login/)
  })
}

test('a refreshed token and a new tab preserve the same backend account', async ({ actor }) => {
  const identity = await actor.page.evaluate(async () => {
    const first = await window.Clerk.session?.getToken()
    const fresh = await window.Clerk.session?.getToken({ skipCache: true })
    return { firstPresent: Boolean(first), freshPresent: Boolean(fresh) }
  })
  expect(identity).toEqual({ firstPresent: true, freshPresent: true })
  const other = await actor.page.context().newPage()
  try {
    await other.goto('/app/settings')
    await expect(other.getByRole('heading', { level: 1 })).toContainText('Settings')
    expect(await actor.api.call('me')).toMatchObject({ id: actor.account.id })
  } finally { await other.close() }
})

test('revoking the current Clerk session removes private content and offers sign-in recovery', async ({ actor, data }) => {
  const deck = await data.create({ name: 'Revoked private collection', type: 'deck' })
  await actor.page.goto(`/app/personal/${deck.id}`)
  await clerk.loaded({ page: actor.page })
  await actor.page.waitForFunction(() => Boolean(window.Clerk.session))
  const id = await actor.page.evaluate(() => window.Clerk.session?.id)
  expect(id).toBeTruthy()
  await createClerkClient({ secretKey: process.env.CLERK_SECRET_KEY! }).sessions.revokeSession(id!)
  await actor.page.reload()
  try {
    await expect(actor.page.getByRole('link', { name: 'Sign in', exact: true })).toBeVisible()
    await expect(actor.page.getByRole('heading', { name: deck.name, exact: true })).not.toBeVisible()
    await actor.page.getByRole('link', { name: 'Sign in', exact: true }).click()
    await expect(actor.page).toHaveURL(/\/login\?returnTo=/)
  } finally {
    await signIn(actor.page, actor.email, actor.password, '/app')
  }
})
