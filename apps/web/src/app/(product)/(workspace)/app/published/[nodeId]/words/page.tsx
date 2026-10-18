import { LibraryPage } from '@/features/library/library-page.client'

export const metadata = { title: 'Published Library · Words' }

export default async function Page({ params }: { params: Promise<{ nodeId: string }> }) {
  const { nodeId } = await params
  return <LibraryPage nodeId={nodeId} routeSpace="published" />
}
