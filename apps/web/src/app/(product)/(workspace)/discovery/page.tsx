import { DiscoveryPage } from '@/features/library/discovery-page.client'

export const metadata = {
  title: 'Discovery', robots: { index: false, follow: true },
  description: 'Explore community decks, folders, and vocabulary collections published by learners on Pycil.',
}

export default function Page() {
  return <DiscoveryPage />
}
