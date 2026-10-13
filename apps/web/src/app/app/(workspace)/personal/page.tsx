import { LibraryPage } from '@/components/library/library-page'
import { Suspense } from 'react'
import { HomeLoading } from '@/components/home/home-state'
import { redirect } from 'next/navigation'
import { libraryHref } from '@/lib/library-model'
import { dehydrate, HydrationBoundary } from '@tanstack/react-query'
import { getQueryClient } from '@/lib/query-client'
import { getServerServices } from '@/lib/services/server'
import { loadServerAccount } from '@/lib/server-account'

export const metadata = { title: 'My Library' }
type Search = { [key: string]: string | string[] | undefined }

async function LibraryRoute({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams
  const node = typeof params.node === 'string' ? params.node : undefined
  const create = typeof params.create === 'string' ? params.create : undefined
  // Existing bookmarks still work, but all material lives at canonical path routes.
  if (node) redirect(libraryHref(node, params.tab === 'meanings' || params.tab === 'words' ? 'words' : 'overview'))

  const queryClient = getQueryClient()
  const account = await loadServerAccount()
  if (account?.personal_node_id) {
    try {
      const services = await getServerServices()
      const scope = account.id
      await queryClient.query({
        queryKey: [services.mode, scope, 'library-node', account.personal_node_id],
        queryFn: async ({ signal }) => {
          try {
            return await services.library.details(account.personal_node_id, signal)
          } catch {
            return await services.library.publicNode(account.personal_node_id, signal)
          }
        },
      }).catch(() => null)
    } catch {
      // Graceful fallback
    }
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <LibraryPage tab="overview" create={create === 'deck' ? 'deck' : create === 'folder' ? 'folder' : undefined} />
    </HydrationBoundary>
  )
}

export default function Page({ searchParams }: { searchParams: Promise<Search> }) {
  return <Suspense fallback={<HomeLoading label="Library" />}><LibraryRoute searchParams={searchParams} /></Suspense>
}
