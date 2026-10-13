import { LibraryRoute } from '@/features/library/server'
import type { SearchValues } from '@/lib/query/url'

export const metadata = { title: 'Published' }
export default async function Page({ searchParams }: { searchParams: Promise<SearchValues> }) {
  return <LibraryRoute space="published" search={await searchParams} words={false} />
}
