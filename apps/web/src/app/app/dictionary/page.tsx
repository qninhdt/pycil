import { DictionaryPage } from '@/components/dictionary/dictionary-page'
export const metadata = { title: 'Dictionary' }
export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q } = await searchParams
  return <DictionaryPage initialQuery={typeof q === 'string' ? q : ''} />
}
