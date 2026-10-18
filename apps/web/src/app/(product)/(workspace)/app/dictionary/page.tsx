import { redirect } from 'next/navigation'
import { searchParams, type SearchValues } from '@/lib/query/url'

export default async function Page({ searchParams: values }: { searchParams: Promise<SearchValues> }) {
  const query = searchParams(await values).toString()
  redirect('/dictionary' + (query ? `?${query}` : ''))
}
