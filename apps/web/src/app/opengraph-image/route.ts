import { socialImage } from '@/features/library/social-image'

export const dynamic = 'force-dynamic'

export function GET() {
  return socialImage('A word is only the beginning.', 'Build a vocabulary library around the meanings that matter to you.')
}
