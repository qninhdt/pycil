import { LibraryRoute } from '@/features/library/server'
import type { SearchValues } from '@/lib/query/url'

export const metadata = { title: 'Library · Words ' }
export default async function Page({ params, searchParams }: { params: Promise<{ nodeId: string }>; searchParams: Promise<SearchValues> }) {
  return <LibraryRoute nodeId={(await params).nodeId} search={await searchParams} words={true} />
}
