import { AppShell } from '@/components/application/app-shell'
import { PublicProfilePage } from '@/components/account/public-profile-page'
export const metadata = { title: 'Published collection' }
export default async function Page({ params }: { params: Promise<{ identifier: string; nodeId: string }> }) {
  const { identifier, nodeId } = await params
  return <AppShell><PublicProfilePage identifier={identifier} nodeId={nodeId} /></AppShell>
}
