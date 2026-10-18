import type { Metadata } from 'next'

export const siteOrigin = (process.env.NEXT_PUBLIC_SITE_URL ?? 'https://pycil.qninhdt.com').replace(/\/$/, '')
export const searchIndexable = process.env.NODE_ENV === 'production' && process.env.VERCEL_ENV !== 'preview' && process.env.NEXT_PUBLIC_DATA_MODE !== 'mock'

export function publicMetadata({ title, description, path, image, index = true }: {
  title: string; description: string; path: string; image?: string; index?: boolean
}): Metadata {
  return {
    title, description,
    alternates: { canonical: `${siteOrigin}${path}` },
    robots: { index: searchIndexable && index, follow: true },
    openGraph: { title, description, url: `${siteOrigin}${path}`, siteName: 'Pycil', type: 'website', images: image ? [{ url: `${siteOrigin}${image}`, width: 1200, height: 630 }] : undefined },
    twitter: { card: 'summary_large_image', title, description, images: image ? [`${siteOrigin}${image}`] : undefined },
  }
}
