import { dataMode } from '@/lib/api/services/config'

export const authConfigured = dataMode === 'live' && Boolean(process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY)
