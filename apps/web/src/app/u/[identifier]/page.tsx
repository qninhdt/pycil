import { AppShell } from '@/components/application/app-shell'
import { PublicProfilePage } from '@/components/account/public-profile-page'
export const metadata = { title: 'Profile' }
export default async function Page({ params }: { params: Promise<{ identifier: string }> }) {
  const { identifier } = await params
  return <AppShell><PublicProfilePage identifier={identifier} /></AppShell>
}
