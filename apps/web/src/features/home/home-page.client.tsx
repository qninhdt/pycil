'use client'

import { useHydrated } from '@/lib/use-hydrated.client'
import { reportingDay } from '@/features/home/calendar'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { Motif } from '@/components/artwork/artwork'
import { useAccount } from '@/features/account/account.client'
import { Button } from '@/components/ui/button'
import { Empty, EmptyHeader, EmptyTitle, EmptyDescription, EmptyContent, EmptyMedia } from '@/components/ui/empty'
import { useTimeOfDay } from '@/components/shell/use-time-of-day.client'
import { useHomeOverview } from '@/features/home/use-home.client'
import type { AccountProfile } from '@/lib/api/account'
import { HomeToday } from './home-today.client'
import { HomeActivity, HomeSchedule, HomeStreak } from './home-history.client'
import { HomeLibrary } from './home-library.client'
import { HomeFailure } from './home-state.client'
import { HomeDashboardSkeleton } from './home-skeletons'

function HomeHeader({ name }: { name?: string | null }) {
  const period = useTimeOfDay()
  const tHome = useTranslations('home')
  const greeting = (value: 'morning' | 'afternoon' | 'night') => {
    const text = value === 'night' ? tHome('goodEvening') : value === 'afternoon' ? tHome('goodAfternoon') : tHome('goodMorning')
    return `${text}${name ? `, ${name}` : ''}`
  }
  return <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border [&_h1]:leading-[1.12] [&_h1]:break-words [&_h1]:text-balance" data-time-of-day={period}>
    <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0"><h1 className="text-[clamp(1.75rem,2.4vw,3rem)] font-extrabold leading-[1.15] tracking-[-.03em] max-[767px]:text-2xl max-[767px]:leading-tight">{(['morning', 'afternoon', 'night'] as const).map(value => <span key={value} className="hidden" data-period={value}>{greeting(value)}<span className="text-art-red" aria-hidden="true">.</span></span>)}</h1></div>
    <div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true"><Motif name="balance" /></div>
  </header>
}

export function HomeDashboard({ profile, initialDay = reportingDay(new Date(), profile.settings.timezone) }: { profile: AccountProfile; initialDay?: string }) {
  const { today, summary, activity, schedule } = useHomeOverview(profile, initialDay)
  return <div className="w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight">
    <HomeHeader name={profile.display_name} />
    <div className="grid grid-cols-[minmax(0,2fr)_minmax(260px,1fr)] border-b border-foreground [&_>_section]:min-w-0 [&_>_section]:p-6 [&_>_section:first-child]:pl-0 [&_>_section:first-child]:border-r [&_>_section:first-child]:border-border [&_>_section:last-child]:pr-0 max-xl:grid-cols-[minmax(0,1.5fr)_minmax(240px,1fr)] max-xl:[&_>_section]:p-5 max-lg:grid-cols-1 max-lg:[&_>_section]:py-6 max-lg:[&_>_section]:px-0 max-lg:[&_>_section:first-child]:border-r-0 max-lg:[&_>_section:first-child]:border-b max-lg:[&_>_section:first-child]:border-border"><HomeToday summary={summary} today={today} /><HomeStreak activity={activity} today={today} /></div>
    <HomeLibrary personalId={profile.personal_node_id} publishedId={profile.published_node_id} />
    <div className="grid grid-cols-[minmax(0,2fr)_minmax(260px,1fr)] border-y border-foreground border-b-border [&_>_section]:min-w-0 [&_>_section]:p-6 [&_>_section:first-child]:pl-0 [&_>_section:first-child]:border-r [&_>_section:first-child]:border-border [&_>_section:last-child]:pr-0 max-xl:grid-cols-[minmax(0,1.5fr)_minmax(240px,1fr)] max-xl:[&_>_section]:p-5 max-lg:grid-cols-1 max-lg:[&_>_section]:py-6 max-lg:[&_>_section]:px-0 max-lg:[&_>_section:first-child]:border-r-0 max-lg:[&_>_section:first-child]:border-b max-lg:[&_>_section:first-child]:border-border"><HomeActivity activity={activity} today={today} /><HomeSchedule schedule={schedule} today={today} /></div>
  </div>
}

export function HomePage({ initialDay }: { initialDay?: string } = {}) {
  const account = useAccount()
  const hydrated = useHydrated()
  const tHome = useTranslations('home')
  const tNav = useTranslations('nav')
  if (!hydrated) return <HomeDashboardSkeleton />
  if (account.status === 'ready' && account.profile) return <HomeDashboard key={account.profile.id} profile={account.profile} initialDay={initialDay} />
  if (account.status === 'loading') return <HomeDashboardSkeleton />
  return <div className="w-full [&_h1]:font-extrabold [&_h1]:tracking-tight [&_h2]:font-extrabold [&_h2]:tracking-tight [&_h3]:font-extrabold [&_h3]:tracking-tight"><HomeHeader />
    {account.status === 'error' ? <HomeFailure label={tNav('yourAccount')} error={new Error(account.error || 'Please retry.')} retry={account.retry} />
      : <Empty className="min-h-[480px] border-y border-foreground [&_[data-slot=empty-icon]]:w-40 [&_[data-slot=empty-icon]]:h-[120px] [&_[data-slot=empty-title]]:text-[28px] [&_[data-slot=empty-title]]:font-extrabold [&_[data-slot=empty-title]]:leading-tight [&_[data-slot=empty-title]]:tracking-tight max-md:px-0"><EmptyHeader><EmptyMedia><Motif name="modular" /></EmptyMedia><EmptyTitle>{tHome('welcomeTitle')}</EmptyTitle><EmptyDescription>{account.status === 'task' ? tHome('welcomeDescTask') : tHome('welcomeDescGuest')}</EmptyDescription></EmptyHeader><EmptyContent>
        <Button asChild variant="red" size="lg"><Link href="/login?returnTo=%2Fapp">{account.status === 'task' ? tHome('continueSetup') : tHome('signInHome')}</Link></Button>
        <Button asChild variant="link"><Link href="/discovery">{tHome('explorePublished')}</Link></Button>
      </EmptyContent></Empty>}
  </div>
}
