'use client'

import { webConfig } from '@/config'

import { useEffect, useState } from 'react'
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useServices } from '@/lib/api/services/provider.client'
import type { AccountProfile } from '@/lib/api/account'
import { homeQueries, libraryPreviewQuery } from '@/features/home/queries'
import { reportingDay } from '@/features/home/calendar'

export type HomeResource<T> = { status: 'loading' | 'ready' | 'error'; data: T | null; error: Error | null; retry: () => void }
function resource<T>(query: UseQueryResult<T, Error>): HomeResource<T> {
  return { status: query.isError ? 'error' : query.isPending ? 'loading' : 'ready', data: query.isError ? null : query.data ?? null, error: query.error,
    retry: () => { void query.refetch() } }
}

function useReportingDay(timezone: string, initialDay: string): string {
  const [value, setValue] = useState({ timezone, day: initialDay })
  useEffect(() => {
    const update = () => {
      const day = reportingDay(new Date(), timezone)
      setValue(current => current.timezone === timezone && current.day === day ? current : { timezone, day })
    }
    update()
    const timer = setInterval(update, webConfig.polling.clockMs)
    window.addEventListener('focus', update)
    return () => { clearInterval(timer); window.removeEventListener('focus', update) }
  }, [timezone])
  return value.timezone === timezone ? value.day : reportingDay(new Date(), timezone)
}

export function useHomeOverview(profile: AccountProfile, initialDay: string) {
  const { services, scope } = useServices()
  const today = useReportingDay(profile.settings.timezone, initialDay)
  const queries = homeQueries(services, scope, profile, today)
  const summary = useQuery(queries.summary), activity = useQuery(queries.activity), schedule = useQuery(queries.schedule)
  return { today, summary: resource(summary), activity: resource(activity), schedule: resource(schedule) }
}

export function useLibraryPreview(parentId: string) {
  const { services, scope } = useServices()
  return resource(useQuery(libraryPreviewQuery(services, scope, parentId)))
}
