import { LibraryRoute } from '@/features/library/server'
import type { SearchValues } from '@/lib/query/url'

export const metadata = { title: 'My Library' }
export default async function Page({ searchParams }: { searchParams: Promise<SearchValues> }) {
  return <LibraryRoute search={await searchParams} />
}
