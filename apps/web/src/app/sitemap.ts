import type { MetadataRoute } from 'next'
import { getPublicServices } from '@/lib/api/services/server'
import { searchIndexable, siteOrigin } from '@/lib/seo'
import { ApiError } from '@/lib/api/error'
import { isDeck, publicCollectionHref } from '@/features/library/model'

export const revalidate = 300

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  if (!searchIndexable) return []
  const services = getPublicServices(), signal = new AbortController().signal
  const result: MetadataRoute.Sitemap = [{ url: siteOrigin }]
  const profiles = new Set<string>()
  // Seed the latest bounded discovery page; deeper material remains crawlable through public links.
  const page = await services.library.discovery({ limit: 50 }, signal)
  for (let offset = 0; offset < page.nodes.length; offset += 5) {
    await Promise.all(page.nodes.slice(offset, offset + 5).map(async candidate => {
      try {
        const node = await services.library.publicNode(candidate.id, signal)
        if (node.reference_available === false) return
        const nonempty = isDeck(node)
          ? (await services.library.meanings(node.id, { limit: 1 }, signal, true)).senses.length
          : (await services.library.contents(node.target?.id ?? node.id, { limit: 1 }, signal, true)).nodes.length
        if (!nonempty) return
        const profile = await services.account.publicProfile(node.owner_id, signal)
        result.push({ url: `${siteOrigin}${publicCollectionHref(profile.handle || profile.id, node.id)}`, lastModified: node.updated_at })
        if (!profiles.has(profile.id)) {
          profiles.add(profile.id)
          result.push({ url: `${siteOrigin}${publicCollectionHref(profile.handle || profile.id)}` })
        }
      } catch (error) {
        // A publication can disappear between discovery and this read.
        if (!(error instanceof ApiError && [403, 404].includes(error.status))) throw error
      }
    }))
  }
  return result
}
