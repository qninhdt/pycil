import { Suspense, type ReactNode } from 'react'
import { HomeLoading } from '@/components/home/home-state'
import { LibraryNodePage } from '@/components/library/library-page'

type NodeLayoutProps = { params: Promise<{ nodeId: string }>; children: ReactNode }

async function NodeLayout({ params, children }: NodeLayoutProps) {
  const { nodeId } = await params
  return <><LibraryNodePage nodeId={nodeId} />{children}</>
}

export default function Layout(props: NodeLayoutProps) {
  return <Suspense fallback={<HomeLoading label="Library" />}><NodeLayout {...props} /></Suspense>
}
