import type { MetadataRoute } from 'next'
import { searchIndexable, siteOrigin } from '@/lib/seo'

export default function robots(): MetadataRoute.Robots {
  return { rules: searchIndexable ? { userAgent: '*', allow: '/', disallow: ['/app/', '/login', '/signup', '/auth/'] } : { userAgent: '*', disallow: '/' }, sitemap: `${siteOrigin}/sitemap.xml` }
}
