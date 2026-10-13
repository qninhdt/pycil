import { Suspense, type ReactNode } from 'react'
import { dehydrate, HydrationBoundary } from '@tanstack/react-query'
import { getQueryClient } from '@/lib/query-client'
import { getServerServices } from '@/lib/services/server'
import { loadServerAccount } from '@/lib/server-account'
import { HomeLoading } from '@/components/home/home-state'
import { LibraryNodePage } from '@/components/library/library-page'

type NodeLayoutProps = { params: Promise<{ nodeId: string }>; children: ReactNode }

async function NodeLayout({ params, children }: NodeLayoutProps) {
  const { nodeId } = await params
  const queryClient = getQueryClient()
  const account = await loadServerAccount()

  if (nodeId) {
    try {
      const services = await getServerServices()
      const scope = account?.id ?? 'signed-out'
      await queryClient.query({
        queryKey: [services.mode, scope, 'library-node', nodeId],
        queryFn: async ({ signal }) => {
          try {
            return await services.library.details(nodeId, signal)
          } catch {
            return await services.library.publicNode(nodeId, signal)
          }
        },
      }).catch(() => null)
    } catch {
      // Graceful fallback to client fetching
    }
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <LibraryNodePage nodeId={nodeId} />
      {children}
    </HydrationBoundary>
  )
}

export default function Layout(props: NodeLayoutProps) {
  return <Suspense fallback={<HomeLoading label="Library" />}><NodeLayout {...props} /></Suspense>
}
