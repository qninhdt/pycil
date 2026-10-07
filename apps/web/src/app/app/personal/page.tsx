import { LibraryPage } from '@/components/library/library-page'
import { Suspense } from 'react'
import { HomeLoading } from '@/components/home/home-state'
import { redirect } from 'next/navigation'
import { libraryHref } from '@/lib/library-model'
export const metadata = { title: 'My Library' }
type Search = { [key: string]: string | string[] | undefined }
async function LibraryRoute({ searchParams }: { searchParams: Promise<Search> }) {
  const params = await searchParams
  const node = typeof params.node === 'string' ? params.node : undefined
  const create = typeof params.create === 'string' ? params.create : undefined
  // Existing bookmarks still work, but all material lives at canonical path routes.
  if (node) redirect(libraryHref(node, params.tab === 'meanings' || params.tab === 'words' ? 'words' : 'overview'))
  return <LibraryPage tab="overview" create={create === 'deck' ? 'DECK' : create === 'folder' ? 'FOLDER' : undefined} />
}
export default function Page({ searchParams }: { searchParams: Promise<Search> }) {
  return <Suspense fallback={<HomeLoading label="Library" />}><LibraryRoute searchParams={searchParams} /></Suspense>
}
