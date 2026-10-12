'use client'

import { useEffect, useState } from 'react'
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useServices } from '@/lib/services/provider'
import type { AccountProfile } from '@/lib/api'
import { reportingDay, shiftDay } from '@/lib/home-calendar'

export type HomeResource<T> = { status: 'loading' | 'ready' | 'error'; data: T | null; error: Error | null; retry: () => void }
function resource<T>(query: UseQueryResult<T, Error>): HomeResource<T> {
  return { status: query.isError ? 'error' : query.isPending ? 'loading' : 'ready', data: query.isError ? null : query.data ?? null, error: query.error,
    retry: () => { void query.refetch() } }
}

function useReportingDay(timezone: string): string | null {
  const [value, setValue] = useState<{ timezone: string; day: string } | null>(null)
  useEffect(() => {
    const update = () => {
      const day = reportingDay(new Date(), timezone)
      setValue(current => current?.timezone === timezone && current.day === day ? current : { timezone, day })
    }
    update()
    const timer = setInterval(update, 60000)
    window.addEventListener('focus', update)
    return () => { clearInterval(timer); window.removeEventListener('focus', update) }
  }, [timezone])
  return value?.timezone === timezone ? value.day : null
}

export function useHomeOverview(profile: AccountProfile) {
  const { services, scope } = useServices()
  const today = useReportingDay(profile.settings?.timezone || 'UTC')
  const start = today ? [`${today.slice(0, 7)}-01`, shiftDay(today, -6)].sort()[0] : ''
  const summary = useQuery({ queryKey: [services.mode, scope, 'progress', profile.library_node_id], queryFn: ({ signal }) => services.learning.summary(undefined, signal), refetchInterval: 60000 })
  const activity = useQuery({ queryKey: [services.mode, scope, 'activity', start, today], enabled: Boolean(today), queryFn: ({ signal }) => services.learning.activity({ start, end: today! }, signal), refetchInterval: 60000 })
  const schedule = useQuery({ queryKey: [services.mode, scope, 'schedule', today], enabled: Boolean(today), queryFn: ({ signal }) => services.learning.schedule({ start: today!, end: shiftDay(today!, 6) }, signal), refetchInterval: 60000 })
  return { today, summary: resource(summary), activity: resource(activity), schedule: resource(schedule) }
}

export function useLibraryPreview(parentId: string) {
  const { services, scope } = useServices()
  return resource(useQuery({ queryKey: [services.mode, scope, 'library-preview', parentId], queryFn: ({ signal }) => services.library.list(parentId, signal) }))
}
