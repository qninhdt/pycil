import { prefetchAuthors } from '@/features/library/authors.server'
import { dehydrateRoute } from '@/lib/query/server'
import { HydrationBoundary } from '@tanstack/react-query'
import { makeQueryClient } from '@/lib/query/client'
import { getServerServices, getServerScope } from '@/lib/api/services/server'
import { loadServerAccount } from '@/lib/auth/account'
import { reportingDay } from '@/features/home/calendar'
import { homeQueries, libraryPreviewQuery } from '@/features/home/queries'
import { HomePage } from '@/features/home/home-page.client'

export const metadata = { title: 'Home' }

export default async function Page() {
  const [account, services, scope] = await Promise.all([loadServerAccount(), getServerServices(), getServerScope()])
  const client = makeQueryClient()
  const today = reportingDay(new Date(), account?.settings.timezone ?? 'UTC')
  if (account) {
    const queries = homeQueries(services, scope, account, today)
    const [, , , personal, published] = await Promise.all([
      client.query(queries.summary), client.query(queries.activity), client.query(queries.schedule),
      client.query(libraryPreviewQuery(services, scope, account.personal_node_id)),
      client.query(libraryPreviewQuery(services, scope, account.published_node_id)),
    ])
    await prefetchAuthors(client, services, scope, [...personal.nodes, ...published.nodes], account.id)
  }
  return <HydrationBoundary state={dehydrateRoute(client)}><HomePage initialDay={today} /></HydrationBoundary>
}
