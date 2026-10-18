'use client'

import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import type { AccountProfile } from '@/lib/api/account'
import type { StudySummary } from '@/lib/api/study'
import { dateLabel, isDeck, nodeHref, publicCollectionHref, type LibraryDetails, type LibraryTab } from './model'
import { LibraryFlashcardPreview } from './library-flashcard-preview.client'
import { LibraryFolder } from './library-folder.client'
import { LibraryWords } from './library-words.client'

export function LibraryContent({ node, profile, summary, editable, publicIdentifier }: {
  node: LibraryDetails; profile: AccountProfile | null; summary?: StudySummary; editable: boolean; publicIdentifier?: string
}) {
  const pathname = usePathname()
  const tab = pathname?.endsWith('/words') ? 'words' : 'overview'
  const t = useTranslations('library')
  const deck = isDeck(node), timezone = profile?.settings?.timezone ?? 'UTC'
  return (
        <Tabs value={tab} onValueChange={value => { const href = publicIdentifier ? publicCollectionHref(publicIdentifier, node.id, value as LibraryTab) : nodeHref(node, value as LibraryTab, profile?.id); if (window.location.pathname !== href) window.history.pushState(null, '', href) }}>
          <TabsList className="mb-3" aria-label="Library view"><TabsTrigger value="overview">{t('overview')}</TabsTrigger><TabsTrigger value="words">{t('words')}</TabsTrigger></TabsList>
          <TabsContent value="overview">{deck ? <div className="grid grid-cols-[minmax(0,2.4fr)_minmax(224px,1fr)] gap-6 border-t border-border pt-5 max-[959px]:grid-cols-1"><LibraryFlashcardPreview key={node.id} nodeId={node.id} total={summary?.total} publicRead={Boolean(publicIdentifier)} /><section className="border-l border-border pl-6 [&_dl]:grid [&_dl]:grid-cols-1 [&_dl_>_div]:flex [&_dl_>_div]:justify-between [&_dl_>_div]:gap-4 [&_dl_>_div]:py-3 [&_dl_>_div]:border-b [&_dl_>_div]:border-border [&_dl_>_div]:text-xs [&_dt]:text-muted-foreground [&_dd]:text-right max-[959px]:border-l-0 max-[959px]:border-t max-[959px]:border-border max-[959px]:pl-0 max-[959px]:pt-5 max-[767px]:[&_dl]:grid-cols-1 max-[767px]:[&_dl]:gap-0" aria-labelledby="library-about-title"><div className="flex items-center justify-between gap-4 mb-3 [&_h2]:text-[19px] [&_h2]:leading-snug"><h2 id="library-about-title">{t('deckDetails')}</h2></div>
              <dl><div><dt>{t('created')}</dt><dd>{dateLabel(node.created_at, timezone)}</dd></div><div><dt>{t('updated')}</dt><dd>{dateLabel(node.updated_at, timezone)}</dd></div>{!publicIdentifier && <div><dt>{t('lastStudied')}</dt><dd>{summary ? dateLabel(summary.last_studied_at, timezone) : '—'}</dd></div>}</dl>
            </section></div> : <LibraryFolder nodeId={node.target?.id ?? node.id} name={node.name} space={node.space === 'published' ? 'published' : 'personal'} publishedBase={publicIdentifier ? publicCollectionHref(node.target?.owner_id ?? publicIdentifier) : undefined} canCreate={node.owner_id === profile?.id && node.type === 'folder' && node.space !== 'library'} />}</TabsContent>
          <TabsContent value="words"><LibraryWords nodeId={node.id} summary={summary} folder={!deck} publicRead={Boolean(publicIdentifier)} editable={editable && node.type !== 'reference'} timezone={timezone} /></TabsContent>
        </Tabs>
  )
}
