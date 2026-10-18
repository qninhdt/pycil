import { LibraryPage } from '@/features/library/library-page.client'
import type { SearchValues } from '@/lib/query/url'

export const metadata = { title: 'Published Library' }

export default async function Page({ searchParams }: { searchParams: Promise<SearchValues> }) {
  const search = await searchParams
  const create = search?.create === 'deck' || search?.create === 'folder' ? search.create : undefined
  return <LibraryPage routeSpace="published" create={create} />
}
