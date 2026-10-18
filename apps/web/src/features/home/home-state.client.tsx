'use client'

import Link from 'next/link'
import { useTranslations } from 'next-intl'
import { AlertCircle, RotateCcw } from '@/components/artwork/artwork'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/lib/api/error'

export function HomeLoading({ label }: { label: string }) {
  const t = useTranslations('home')
  return <div className="flex flex-col gap-5 min-h-[196px] py-6 w-full animate-in fade-in duration-150" role="status" aria-label={t('loadingLabelAria', { label })}>
    <div className="flex flex-col gap-2">
      <Skeleton className="h-8 w-48 max-w-full" aria-hidden="true" />
      <Skeleton className="h-4 w-72 max-w-full" aria-hidden="true" />
    </div>
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 pt-2">
      <Skeleton className="h-36 w-full" aria-hidden="true" />
      <Skeleton className="h-36 w-full" aria-hidden="true" />
      <Skeleton className="h-36 w-full" aria-hidden="true" />
    </div>
    <span className="sr-only">{t('loadingLabelSr', { label })}</span>
  </div>
}

export function HomeFailure({ label, error, retry }: { label: string; error: Error | null; retry: () => void }) {
  const t = useTranslations('home')
  const tNav = useTranslations('nav')
  const tCommon = useTranslations('common')
  const expired = error instanceof ApiError && error.status === 401
  const large = error instanceof ApiError && error.code === 'scope_too_large'
  return <Alert className="[&_[data-slot=alert-description]]:flex [&_[data-slot=alert-description]]:flex-col [&_[data-slot=alert-description]]:items-start [&_[data-slot=alert-description]]:gap-4">
    <AlertCircle aria-hidden="true" />
    <AlertTitle>{t('couldNotLoadLabel', { label })}</AlertTitle>
    <AlertDescription>
      <p>{error?.message || t('pleaseTryAgain')}</p>
      {expired || large ? <Button asChild variant="outline"><Link href={expired ? '/login?returnTo=%2Fapp' : '/app/personal'}>{expired ? tNav('signInAgain') : t('openLibrary')}</Link></Button>
        : <Button variant="outline" onClick={retry}><RotateCcw data-icon="inline-start" aria-hidden="true" />{tCommon('retry')}</Button>}
    </AlertDescription>
  </Alert>
}

export function StatusShape({ state }: { state: 'due' | 'new' | 'not-due' }) {
  return <svg className="home-status-shape size-4 shrink-0 max-[767px]:size-3" viewBox="0 0 20 20" aria-hidden="true" data-status={state}>
    {state === 'due' ? <circle cx="10" cy="10" r="9" fill="var(--art-red)" />
      : state === 'new' ? <path d="M10 1 20 19H0Z" fill="var(--art-yellow)" />
      : <path d="M1 1h18v18H1Z" fill="var(--art-blue)" />}
  </svg>
}
