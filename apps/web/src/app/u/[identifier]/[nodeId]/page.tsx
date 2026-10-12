import { redirect } from 'next/navigation'
import { publishedHref } from '@/lib/library-model'

export const metadata = { title: 'Published collection' }

export default async function Page({ params }: { params: Promise<{ identifier: string; nodeId: string }> }) {
  const { identifier, nodeId } = await params
  redirect(publishedHref(identifier, nodeId))
}
