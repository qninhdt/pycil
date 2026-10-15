const id = process.argv[2]
if (!id || !/^[a-z0-9]{12,40}$/.test(id)) throw new Error('Pass one recorded E2E run ID')
process.env.E2E_RUN_ID = id
const { credentials } = await import('./environment.ts')
const { requireFreePort } = await import('./stack.ts')
credentials(false)
await requireFreePort(3200)
const { cleanupIdentities } = await import('../fixtures/users.ts')
await cleanupIdentities()
console.log(`Reconciled only Clerk identities recorded for run ${id}.`)
export {}
