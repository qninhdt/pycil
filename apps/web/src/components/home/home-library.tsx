'use client'

import { useState } from 'react'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { ArrowUpRight } from '@/components/artwork/artwork'
import { LibraryNodeIcon } from '@/components/library/library-node-icon'
import { libraryHref, libraryNodeLabel, publishedHref } from '@/lib/library-model'
import { useAccount } from '@/components/application/providers'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription } from '@/components/ui/empty'
import { useLibraryPreview } from '@/hooks/use-learning'
import { HomeFailure, HomeLoading, StatusShape } from './home-state'

export function HomeLibrary({ personalId, publishedId }: { personalId: string; publishedId: string }) {
  const account = useAccount()
  const t = useTranslations('home')
  const [space, setSpace] = useState('personal')
  const parent = space === 'personal' ? personalId : publishedId
  const library = useLibraryPreview(parent)

  return <section className="py-8 [&_>div:first-child]:mb-3 max-md:[&_>div:first-child]:gap-2 max-[380px]:[&_>div:first-child]:items-start max-[380px]:[&_>div:first-child]:flex-col" aria-labelledby="home-library-title">
    <div className="flex items-center justify-between gap-4 mb-6 [&_h2]:text-[22px] [&_h2]:leading-snug [&_h3]:text-lg [&_h3]:leading-snug [&_p]:text-muted-foreground [&_p]:text-[13px] [&_p]:mt-1.5 max-md:[&_h2]:text-xl"><h2 id="home-library-title">{t('fromYourLibrary')}</h2><Button asChild variant="link"><Link href={space === 'published' && account.profile ? publishedHref(account.profile.id) : libraryHref()}>{space === 'published' ? t('viewPublished') : t('viewLibrary')}<ArrowUpRight data-icon="inline-end" aria-hidden="true" /></Link></Button></div>
    <Tabs value={space} onValueChange={setSpace}><TabsList aria-label={t('fromYourLibrary')}><TabsTrigger value="personal">{t('personal')}</TabsTrigger><TabsTrigger value="published">{t('published')}</TabsTrigger></TabsList>
      {['personal', 'published'].map(value => <TabsContent key={value} value={value}>
        {library.status === 'loading' ? <HomeLoading label={space === 'personal' ? t('personalLibraryLabel') : t('publishedLibraryLabel')} /> : library.status === 'error' ? <HomeFailure label={space === 'personal' ? t('personalLibraryLabel') : t('publishedLibraryLabel')} error={library.error} retry={library.retry} />
          : library.data?.nodes.length === 0 ? <Empty className="min-h-[196px]"><EmptyHeader><EmptyTitle>{space === 'personal' ? t('emptyLibraryTitle') : t('emptyPublishedTitle')}</EmptyTitle><EmptyDescription>{space === 'personal' ? t('emptyLibraryDesc') : t('emptyPublishedDesc')}</EmptyDescription></EmptyHeader></Empty>
          : <ul className="mt-3 [&_>_li]:border-t [&_>_li]:border-border [&_>_li:last-child]:border-b [&_>_li:last-child]:border-border">{library.data?.nodes.map(node => <li key={node.id}>
            <Link href={space === 'published' ? publishedHref(node.owner_id ?? account.profile?.id ?? 'me', node.id) : libraryHref(node.id)} className="grid grid-cols-[40px_minmax(0,1fr)_auto_20px] items-center gap-[18px] px-2 py-5 no-underline transition-colors duration-160 hover:bg-accent max-lg:grid-cols-[32px_minmax(0,1fr)_18px] max-lg:gap-3">
              <span className="[&_>_.bauhaus-icon]:size-8 max-lg:row-span-2"><LibraryNodeIcon node={node} /></span>
              <div className="min-w-0 [&_h3]:text-base [&_h3]:break-words [&_h3]:leading-snug [&_p]:text-xs [&_p]:text-muted-foreground [&_p]:mt-1"><h3>{node.name}</h3><p>{libraryNodeLabel(node)}{node.summary && <> · {node.summary.total.toLocaleString('en')} {t('wordsCount')}</>}</p></div>
              <div className="flex items-center gap-6 text-xs [&_>_span]:inline-flex [&_>_span]:items-center [&_>_span]:gap-1.5 [&_>_span]:whitespace-nowrap [&_.home-status-shape]:size-2.5 max-lg:col-start-2 max-lg:row-start-2 max-lg:gap-4">{node.summary ? <><span><StatusShape state="due" /><strong>{node.summary.due}</strong> {t('dueNow')}</span><span><StatusShape state="new" /><strong>{node.summary.new}</strong> {t('new')}</span></> : <span>{t('summaryUnavailable')}</span>}</div>
              <ArrowUpRight className="size-[18px] max-lg:col-start-3 max-lg:row-span-2" aria-hidden="true" />
            </Link>
          </li>)}</ul>}
      </TabsContent>)}
    </Tabs>
  </section>
}
