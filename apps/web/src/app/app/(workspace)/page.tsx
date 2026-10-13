import { dehydrate, HydrationBoundary } from '@tanstack/react-query'
import { getQueryClient } from '@/lib/query-client'
import { getServerServices } from '@/lib/services/server'
import { loadServerAccount } from '@/lib/server-account'
import { reportingDay, shiftDay } from '@/lib/home-calendar'
import { HomePage } from '@/components/home/home-page'

export const metadata = { title: 'Home' }

export default async function Page() {
  const queryClient = getQueryClient()
  const account = await loadServerAccount()

  if (account) {
    try {
      const services = await getServerServices()
      const scope = account.id
      const tz = account.settings?.timezone || 'UTC'
      const today = reportingDay(new Date(), tz)
      const start = [`${today.slice(0, 7)}-01`, shiftDay(today, -6)].sort()[0]

      await Promise.allSettled([
        queryClient.query({
          queryKey: [services.mode, scope, 'progress', account.library_node_id],
          queryFn: ({ signal }) => services.learning.summary(undefined, signal),
        }),
        queryClient.query({
          queryKey: [services.mode, scope, 'activity', start, today],
          queryFn: ({ signal }) => services.learning.activity({ start, end: today }, signal),
        }),
        queryClient.query({
          queryKey: [services.mode, scope, 'schedule', today],
          queryFn: ({ signal }) => services.learning.schedule({ start: today, end: shiftDay(today, 6) }, signal),
        }),
        queryClient.query({
          queryKey: [services.mode, scope, 'library-preview', account.personal_node_id],
          queryFn: ({ signal }) => services.library.list(account.personal_node_id, signal),
        }),
        queryClient.query({
          queryKey: [services.mode, scope, 'library-preview', account.published_node_id],
          queryFn: ({ signal }) => services.library.list(account.published_node_id, signal),
        }),
      ])
    } catch {
      // Graceful fallback to client fetching
    }
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <HomePage />
    </HydrationBoundary>
  )
}
