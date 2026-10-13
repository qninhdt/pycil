import { createServer } from 'node:net'
import { mkdir, writeFile } from 'node:fs/promises'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { userInfo } from 'node:os'
import { DockerComposeEnvironment, Wait } from 'testcontainers'
import { artifacts, credentials, directory, runId } from './environment.ts'

export async function requireFreePort(port: number) {
  const server = createServer()
  await new Promise<void>((resolve, reject) => {
    server.once('error', () => reject(new Error(`Reserved E2E port ${port} is occupied`)))
    server.listen(port, '127.0.0.1', () => server.close(error => error ? reject(error) : resolve()))
  })
}

export async function startStack(live: boolean) {
  await Promise.all([requireFreePort(8100), ...(!live ? [requireFreePort(8110)] : [])])
  await mkdir(artifacts, { recursive: true, mode: 0o700 })
  const environment = {
    ...credentials(live), E2E_RUN_ID: runId,
    E2E_ARTIFACTS: artifacts, E2E_UID: String(userInfo().uid), E2E_GID: String(userInfo().gid),
    CLERK_AUDIENCE: process.env.CLERK_AUDIENCE ?? '',
    ...(!live ? {
      LLM_API_KEY: 'controlled-e2e', LLM_BASE_URL: 'http://provider:8110',
      DECISION_API_KEY: 'controlled-e2e', DECISION_BASE_URL: 'http://provider:8110/decisions',
    } : {}),
  }
  const project = `pycil-e2e-${runId}`
  const compose = new DockerComposeEnvironment(`${directory}/support`, 'compose.yaml')
    .withEnvironment(environment).withProjectName(project).withBuild()
    .withStartupTimeout(180_000)
    .withWaitStrategy('migration-1', Wait.forOneShotStartup())
    .withWaitStrategy('baseline-1', Wait.forOneShotStartup())
  if (!live) compose.withProfiles('controlled')
  try {
    const stack = await compose.up()
    try {
      // Exited dependency containers are omitted by Testcontainers' running-container list.
      for (const service of ['migration', 'baseline']) {
        const { stdout } = await promisify(execFile)('docker', ['inspect', '--format', '{{json .State}}', `${project}-${service}-1`], { timeout: 10_000 })
        const state = JSON.parse(stdout) as { Status: string; ExitCode: number }
        if (state.Status !== 'exited' || state.ExitCode !== 0) throw new Error(`${service} did not complete successfully`)
      }
      const container = stack.getContainer('api-1')
      await writeFile(`${artifacts}/runtime.json`, JSON.stringify({ runId, project, apiContainer: container.getId() }), { mode: 0o600 })
      return stack
    } catch (cause) {
      try { await stack.down() }
      catch { throw new AggregateError([cause, new Error(`Cleanup failed for owned Compose project ${project}`)], 'E2E post-start validation and cleanup failed') }
      throw cause
    }
  } catch (cause) {
    // Compose can fail before its wait strategies register cleanup.
    try {
      const { stdout } = await promisify(execFile)('docker', ['compose', '-p', project, '-f', `${directory}/support/compose.yaml`, 'logs', '--no-color'], {
        env: { ...process.env, ...environment }, timeout: 30_000, maxBuffer: 4 * 1024 * 1024,
      })
      await writeFile(`${artifacts}/setup.log`, stdout, { mode: 0o600 })
    } catch { /* Preserve the original startup failure if diagnostics are unavailable. */ }
    try {
      await promisify(execFile)('docker', ['compose', '-p', project, '-f', `${directory}/support/compose.yaml`, 'down', '--volumes', '--remove-orphans'], {
        env: { ...process.env, ...environment }, timeout: 30_000,
      })
    } catch {
      throw new AggregateError([cause, new Error(`Cleanup failed for owned Compose project ${project}`)], 'E2E startup and cleanup failed')
    }
    throw cause
  }
}
