import Link from 'next/link'
import { AlertCircle, RotateCcw } from '@/components/artwork/artwork'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { HomeApiError } from '@/lib/home-api'

export function HomeLoading({ label }: { label: string }) {
  return <div className="flex flex-col gap-5 min-h-[196px] py-6" role="status" aria-label={`Loading ${label}`}>
    <Skeleton className="h-10 w-2/5" aria-hidden="true" />
    <Skeleton className="h-4 w-4/5" aria-hidden="true" />
    <Skeleton className="h-4 w-3/5" aria-hidden="true" />
    <span className="sr-only">Loading {label}.</span>
  </div>
}

export function HomeFailure({ label, error, retry }: { label: string; error: Error | null; retry: () => void }) {
  const expired = error instanceof HomeApiError && error.status === 401
  const large = error instanceof HomeApiError && error.code === 'scope_too_large'
  return <Alert className="[&_[data-slot=alert-description]]:flex [&_[data-slot=alert-description]]:flex-col [&_[data-slot=alert-description]]:items-start [&_[data-slot=alert-description]]:gap-4">
    <AlertCircle aria-hidden="true" />
    <AlertTitle>Could not load {label}.</AlertTitle>
    <AlertDescription>
      <p>{error?.message || 'Please try again.'}</p>
      {expired || large ? <Button asChild variant="outline"><Link href={expired ? '/login?returnTo=%2Fapp' : '/app/personal'}>{expired ? 'Sign in again' : 'Open Library'}</Link></Button>
        : <Button variant="outline" onClick={retry}><RotateCcw data-icon="inline-start" aria-hidden="true" />Retry</Button>}
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
