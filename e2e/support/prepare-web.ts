import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { artifacts, root, runId } from './environment.ts'

export function buildDirectory(web: string, id: string) {
  if (!/^[a-z0-9]{12,40}$/.test(id)) throw new Error('Pass one recorded E2E run ID')
  return `${web}/.e2e/${id}`
}

export async function prepareBuild(web: string, id: string) {
  const directory = buildDirectory(web, id)
  // Exclusive creation preserves the original declarations if setup is repeated.
  await mkdir(directory, { recursive: false, mode: 0o700 })
  const nextEnv = await readFile(`${web}/next-env.d.ts`, 'utf8').catch((error: NodeJS.ErrnoException) => {
    if (error.code !== 'ENOENT') throw error
    return null
  })
  await writeFile(`${directory}/next-env.json`, JSON.stringify(nextEnv), { mode: 0o600 })
  await writeFile(`${directory}/tsconfig.json`, JSON.stringify({
    extends: '../../tsconfig.json',
    compilerOptions: {
      types: ['node', 'next', 'next/image-types/global'],
      tsBuildInfoFile: './tsconfig.tsbuildinfo',
    },
    include: ['../../next-env.d.ts', '../../src/**/*.ts', '../../src/**/*.tsx', '../../tests/**/*.ts', '../../tests/**/*.tsx', './next/types/**/*.ts'],
    exclude: ['../../node_modules'],
  }, null, 2))
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await mkdir(artifacts, { recursive: true, mode: 0o700 })
  await mkdir(`${root}/apps/web/.e2e`, { recursive: true, mode: 0o700 })
  await prepareBuild(`${root}/apps/web`, runId)
}
