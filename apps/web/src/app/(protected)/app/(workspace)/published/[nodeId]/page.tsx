import { LibraryNodePage } from '@/features/library/library-page.client'

export const metadata = { title: 'Published Library · Overview' }

export default async function Page({ params }: { params: Promise<{ nodeId: string }> }) {
  const { nodeId } = await params
  return <LibraryNodePage nodeId={nodeId} routeSpace="published" />
}
