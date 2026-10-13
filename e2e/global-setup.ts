import { clerkSetup } from '@clerk/testing/playwright'
import { startStack } from './support/stack.ts'
import { cleanupIdentities } from './fixtures/actors.ts'
import { writeFile } from 'node:fs/promises'
import { artifacts, providerURL } from './support/environment.ts'

export default async function globalSetup() {
  if (!process.env.CLERK_SECRET_KEY) {
    console.error('CLERK_SECRET_KEY is missing in globalSetup!')
  }
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      await clerkSetup({ dotenv: false })
      break
    } catch (err) {
      if (attempt >= 2) throw err
      console.warn(`clerkSetup attempt ${attempt + 1} failed, retrying...`)
      await new Promise(r => setTimeout(r, 1000 * (attempt + 1)))
    }
  }
  const stack = await startStack(process.env.E2E_PROVIDER_PROFILE === 'live')
  return async () => {
    const errors: unknown[] = []
    if (process.env.E2E_PROVIDER_PROFILE !== 'live') {
      try {
        const response = await fetch(`${providerURL}/unexpected`, { signal: AbortSignal.timeout(5_000) })
        if (!response.ok) throw new Error('Controlled provider diagnostics unavailable')
        const requests = await response.json() as unknown[]
        if (requests.length) throw new Error(`${requests.length} unexpected model request(s) during E2E`)
      } catch (error) { errors.push(error) }
    }
    const results = await Promise.allSettled([cleanupIdentities(), stack.down()])
    const failures = results.filter(result => result.status === 'rejected')
    errors.push(...failures.map(result => result.reason))
    await writeFile(`${artifacts}/cleanup.json`, JSON.stringify({ completed: failures.length === 0 }), { mode: 0o600 })
    if (errors.length) throw new AggregateError(errors, 'E2E verification/cleanup failed')
  }
}
