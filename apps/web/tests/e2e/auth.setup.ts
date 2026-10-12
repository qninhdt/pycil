import { clerkSetup } from '@clerk/testing/playwright'
import { test } from '@playwright/test'

test('configure the official Clerk bot-protection testing token', async () => {
  await clerkSetup()
})
