import { publicSocialImage } from '@/features/library/social-image'

export const dynamic = 'force-dynamic'

export function GET(_request: Request, context: Parameters<typeof publicSocialImage>[0]) {
  return publicSocialImage(context)
}
