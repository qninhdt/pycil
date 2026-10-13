import { AppShell } from '@/components/application/app-shell'
import { PublicNodeView } from '@/components/library/published-route'

export const metadata = { title: 'Published collection' }

export default async function Page({ params }: { params: Promise<{ identifier: string; nodeId: string }> }) {
  const { identifier, nodeId } = await params
  return <AppShell><PublicNodeView identifier={identifier} nodeId={nodeId} /></AppShell>
}
