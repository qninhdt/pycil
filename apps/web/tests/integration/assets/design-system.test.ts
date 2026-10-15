import { expect,test } from 'vitest'

import { readFileSync,readdirSync } from 'node:fs'

import { resolve } from 'node:path'

test('palette literals exactly match DESIGN.md', () => {
  const design = readFileSync(resolve('../../DESIGN.md'), 'utf8')
  const palette = readFileSync(resolve('src/app/globals.css'), 'utf8')
  const source = design.split('typography:')[0]
  for (const match of source.matchAll(/^  ([\w-]+): "(#[\da-f]+)"/gmi)) {
    expect(palette).toContain(`--palette-${match[1]}: ${match[2]};`)
  }
  const theme = palette.slice(palette.indexOf('@custom-variant dark'))
  expect(theme).not.toMatch(/#[\da-f]{3,8}\b/i)
  const art = readFileSync(resolve('src/components/artwork/artwork.tsx'), 'utf8')
  expect(art).not.toMatch(/#[\da-f]{3,8}\b/i)
})

test('every installed shadcn family has a showcase reference', () => {
  const installed = readdirSync('src/components/ui').filter(name => name.endsWith('.tsx') && !name.endsWith('.stories.tsx'))
  expect(installed).toHaveLength(61)
  const source = readdirSync('src/app/(public)/showcase/examples').filter(name => name.endsWith('.tsx')).map(name => readFileSync(`src/app/(public)/showcase/examples/${name}`, 'utf8')).join('\n')
  const renderedSource = source + readFileSync('src/lib/preferences/ui-provider.client.tsx', 'utf8')
  for (const file of installed) expect(renderedSource, `${file} should have a reachable showcase import`).toContain(`@/components/ui/${file.replace('.tsx', '')}`)
})
