import type { Metadata } from 'next'
import { AppShell } from '@/components/application/app-shell'
import { PublicProfilePage } from '@/components/account/public-profile-page'

export async function generateMetadata({
  params,
}: {
  params: Promise<{ identifier: string }>
}): Promise<Metadata> {
  const { identifier } = await params
  return {
    title: `${identifier} — Profile`,
    description: `Public collections and vocabulary profile for ${identifier} on Pycil.`,
  }
}

export default async function Page({ params }: { params: Promise<{ identifier: string }> }) {
  const { identifier } = await params
  return (
    <AppShell>
      <PublicProfilePage identifier={identifier} publishedBase={`/u/${encodeURIComponent(identifier)}`} />
    </AppShell>
  )
}
