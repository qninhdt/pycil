import { afterEach, expect, test, vi } from 'vitest'

vi.mock('server-only', () => ({}))
const services = vi.hoisted(() => ({ library: { discovery: vi.fn(), publicNode: vi.fn(), meanings: vi.fn(), contents: vi.fn() }, account: { publicProfile: vi.fn() } }))
vi.mock('@/lib/api/services/server', () => ({ getPublicServices: () => services }))

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); vi.resetAllMocks() })

test('sitemap excludes empty, unavailable and withdrawn material and prefers canonical handles', async () => {
  await import('@/features/library/model')
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('NEXT_PUBLIC_DATA_MODE', 'live')
  vi.stubEnv('VERCEL_ENV', 'production')
  services.library.discovery.mockResolvedValue({ nodes: ['deck', 'folder', 'empty', 'withdrawn', 'unavailable'].map(id => ({ id })) })
  const { ApiError } = await import('@/lib/api/error')
  services.library.publicNode.mockImplementation(async (id: string) => {
    if (id === 'withdrawn') throw new ApiError(404, 'node_not_found')
    return { id, owner_id: 'owner', type: id === 'folder' ? 'folder' : 'deck', updated_at: '2026-10-19T00:00:00Z', reference_available: id !== 'unavailable' }
  })
  services.library.meanings.mockImplementation(async (id: string) => ({ senses: id === 'empty' ? [] : [{}] }))
  services.library.contents.mockResolvedValue({ nodes: [{}] })
  services.account.publicProfile.mockResolvedValue({ id: 'owner', handle: 'author' })
  const sitemap = (await import('@/app/sitemap')).default
  const entries = await sitemap()
  const { siteOrigin } = await import('@/lib/seo')
  expect(entries.map(item => item.url).sort()).toEqual(['', '/u/author', '/u/author/deck', '/u/author/folder'].map(path => siteOrigin + path).sort())
  expect(services.library.meanings.mock.calls.every(call => call[3] === true)).toBe(true)
  expect(services.library.contents.mock.calls.every(call => call[3] === true)).toBe(true)
  services.library.discovery.mockRejectedValue(new Error('database unavailable'))
  await expect(sitemap()).rejects.toThrow('database unavailable')
})

test('mock and preview deployments are not indexed or enumerated', async () => {
  await import('@/features/library/model')
  vi.stubEnv('NODE_ENV', 'production')
  vi.stubEnv('VERCEL_ENV', 'preview')
  const { publicMetadata } = await import('@/lib/seo')
  expect(publicMetadata({ title: 'Public', description: 'Public content', path: '/u/author' }).robots).toEqual({ index: false, follow: true })
  expect(await (await import('@/app/sitemap')).default()).toEqual([])
  expect(services.library.discovery).not.toHaveBeenCalled()
})
