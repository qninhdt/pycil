import type { Page } from '@playwright/test'
import { build } from 'esbuild'
import { initialUiScript } from '../../../../src/lib/ui-preferences'

const link = `import {forwardRef} from 'react'; export default forwardRef(function Link({prefetch,replace,scroll,locale,...props},ref){return <a {...props} ref={ref}/>})`
const navigation = `export function usePathname(){return '/app'}`

export async function buildFixture(entry: string, platform: Record<string, string> = {}) {
  const modules = { 'next/link': link, 'next/navigation': navigation, ...platform }
  const result = await build({
    entryPoints: [`tests/integration/browser/fixtures/${entry}.tsx`],
    bundle: true, write: false, platform: 'browser', format: 'iife', jsx: 'automatic',
    define: { 'process.env.NODE_ENV': '"production"', 'process.env': '{}' },
    logLevel: 'silent', loader: { '.css': 'empty' },
    plugins: [{ name: 'fixture-platform', setup(builder) {
      builder.onResolve({ filter: /.*/ }, args => Object.hasOwn(modules, args.path) ? { path: args.path, namespace: 'fixture-platform' } : undefined)
      builder.onLoad({ filter: /.*/, namespace: 'fixture-platform' }, args => ({ loader: 'tsx', resolveDir: process.cwd(), contents: modules[args.path as keyof typeof modules] }))
    } }],
  })
  return result.outputFiles[0].text
}

export async function renderFixture(page: Page, bundle: string, name: string, query = '') {
  await page.goto('/app')
  const styles = await page.locator('link[rel=stylesheet]').evaluateAll(nodes => nodes.map(node => (node as HTMLLinkElement).href))
  const path = `/__${name}_fixture__`
  await page.route(`**${path}/bundle.js`, route => route.fulfill({ contentType: 'application/javascript', body: bundle }))
  await page.route(url => url.pathname === path, route => route.fulfill({ contentType: 'text/html', body:
    `<!doctype html><html lang="en"><head><script>${initialUiScript}</script>${styles.map(href => `<link rel="stylesheet" href="${href}">`).join('')}</head><body><div id="fixture"></div><script src="${path}/bundle.js"></script></body></html>` }))
  await page.goto(`${path}${query}`)
}
