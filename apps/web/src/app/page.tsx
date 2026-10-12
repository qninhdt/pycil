import type { Metadata } from 'next'
import { LandingPage } from '@/components/landing/landing-page'

export const metadata: Metadata = {
  title: 'Pycil — A word is only the beginning',
  description: 'Build a vocabulary library around the meanings that matter to you. Practice in context and return when a review is due.',
}

export default function Index() {
  return <LandingPage />
}
