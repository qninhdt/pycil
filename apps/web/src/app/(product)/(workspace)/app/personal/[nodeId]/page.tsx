import { LibraryPage } from '@/features/library/library-page.client'

export const metadata = { title: 'Personal Library · Overview' }

export default async function Page({ params }: { params: Promise<{ nodeId: string }> }) {
  const { nodeId } = await params
  return <LibraryPage nodeId={nodeId} routeSpace="personal" />
}
