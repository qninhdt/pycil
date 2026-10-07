import { Suspense, type ReactNode } from 'react'
import { HomeLoading } from '@/components/home/home-state'
import { PublishedNodeTab } from './published-node-tab'

type Props = { params: Promise<{ identifier: string; nodeId: string }>; children: ReactNode }

export default async function Layout({ params, children }: Props) {
  const { identifier, nodeId } = await params
  return <Suspense fallback={<HomeLoading label="Published library" />}><PublishedNodeTab identifier={identifier} nodeId={nodeId} />{children}</Suspense>
}
