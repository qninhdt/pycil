'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { ArrowUpRight } from '@/components/artwork/artwork'
import { Motif, type MotifName } from '@/components/artwork/artwork'

const motifs: Record<string, MotifName> = {
  home: 'balance',
  dictionary: 'orbit',
  library: 'modular',
  discovery: 'interlock',
  profile: 'counterform',
  settings: 'axis',
}

export function Placeholder({ page, create }: { page: keyof typeof motifs; create?: string }) {
  const t = useTranslations('placeholder')
  const motif = motifs[page]
  const action = create === 'deck' ? t('deckCreation') : create === 'folder' ? t('folderCreation') : null
  const title = page === 'home' ? t('homeTitle') : page === 'dictionary' ? t('dictionaryTitle') : page === 'library' ? t('libraryTitle') : page === 'discovery' ? t('discoveryTitle') : page === 'profile' ? t('profileTitle') : t('settingsTitle')
  const description = page === 'home' ? t('homeDesc') : page === 'dictionary' ? t('dictionaryDesc') : page === 'library' ? t('libraryDesc') : page === 'discovery' ? t('discoveryDesc') : page === 'profile' ? t('profileDesc') : t('settingsDesc')
  const detail = page === 'home' ? t('homeDetail') : page === 'dictionary' ? t('dictionaryDetail') : page === 'library' ? t('libraryDetail') : page === 'discovery' ? t('discoveryDetail') : page === 'profile' ? t('profileDetail') : t('settingsDetail')

  return <div className="w-full">
    <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12]"><div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0"><h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px] text-balance">{title}<span className="text-art-red" aria-hidden="true">.</span></h1><p className="mt-1.5 text-sm leading-[1.6] text-muted-foreground max-md:text-xs">{description}</p></div><div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><Motif name={motif} /></div></header>
    <section className="max-w-[620px] pb-16 pt-[72px] max-md:py-12" aria-label={t('statusAria')}>
      <div className="mb-8 flex gap-[5px]" aria-hidden="true"><span className="h-[5px] w-8 bg-art-red" /><span className="h-[5px] w-8 bg-art-blue" /><span className="h-[5px] w-8 bg-art-yellow" /></div>
      <h2 className="text-[28px] font-bold leading-[1.2] tracking-[-.025em] max-md:text-[25px]">{action ? t('actionNext', { action }) : t('foundationInPlace')}</h2>
      <p className="mt-4 max-w-[50ch] text-sm leading-[1.8] text-muted-foreground">{action ? t('actionDesc') : t('pageDesc')} {detail}</p>
      <Link href="/showcase" className="mt-8 inline-flex min-h-11 items-center gap-2.5 text-[13px] font-semibold underline underline-offset-[6px] [&_svg]:size-4">{t('exploreWorkshop')} <ArrowUpRight aria-hidden="true" /></Link>
    </section>
  </div>
}
