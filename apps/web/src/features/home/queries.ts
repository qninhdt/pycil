import { queryOptions } from '@tanstack/react-query'
import type { AccountProfile } from '@/lib/api/account'
import type { FrontendServices } from '@/lib/api/services/contracts'
import { shiftDay } from '@/features/home/calendar'

export function homeQueries(services: FrontendServices, scope: string, profile: AccountProfile, today: string) {
  const start = [`${today.slice(0, 7)}-01`, shiftDay(today, -6)].sort()[0]
  return {
    summary: queryOptions({ queryKey: [services.mode, scope, 'progress', profile.library_node_id], queryFn: ({ signal }) => services.learning.summary(undefined, signal), refetchInterval: 60000 }),
    activity: queryOptions({ queryKey: [services.mode, scope, 'activity', start, today], queryFn: ({ signal }) => services.learning.activity({ start, end: today }, signal), refetchInterval: 60000 }),
    schedule: queryOptions({ queryKey: [services.mode, scope, 'schedule', today], queryFn: ({ signal }) => services.learning.schedule({ start: today, end: shiftDay(today, 6) }, signal), refetchInterval: 60000 }),
  }
}

export function libraryPreviewQuery(services: FrontendServices, scope: string, parentId: string) {
  return queryOptions({ queryKey: [services.mode, scope, 'library-preview', parentId], queryFn: ({ signal }) => services.library.list(parentId, signal) })
}
