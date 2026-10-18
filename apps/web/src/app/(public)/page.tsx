import type { Metadata } from 'next'
import { publicMetadata } from '@/lib/seo'
import { LandingPage } from '@/components/landing/landing-page'

export const metadata: Metadata = {
  ...publicMetadata({ title: 'Pycil — A word is only the beginning', description: 'Build a vocabulary library around the meanings that matter to you. Practice in context and return when a review is due.', path: '/', image: '/opengraph-image' }),
  title: { absolute: 'Pycil — A word is only the beginning' },
  description: 'Build a vocabulary library around the meanings that matter to you. Practice in context and return when a review is due.',
}

export default async function Index() {
  return <LandingPage />
}
