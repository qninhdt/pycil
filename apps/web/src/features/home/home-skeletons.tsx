import { Skeleton } from '@/components/ui/skeleton'
import { Motif } from '@/components/artwork/artwork'

export function HomeHeaderSkeleton() {
  return (
    <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border">
      <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0 space-y-2">
        <Skeleton className="h-10 w-64 max-w-full" />
      </div>
      <div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true">
        <Motif name="balance" />
      </div>
    </header>
  )
}

export function TodaySkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading today counts">
      <dl className="grid grid-cols-[1.2fr_1fr_1fr] gap-5 items-end my-7 max-xl:gap-3 max-md:my-4 max-md:gap-2 max-md:grid-cols-3">
        <div className="space-y-2">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-16 w-24 max-md:h-10" />
          <Skeleton className="h-3 w-28 max-w-full" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-4 w-12" />
          <Skeleton className="h-12 w-20 max-md:h-10" />
          <Skeleton className="h-3 w-24 max-w-full" />
        </div>
        <div className="space-y-2">
          <Skeleton className="h-4 w-16" />
          <Skeleton className="h-12 w-20 max-md:h-10" />
          <Skeleton className="h-3 w-24 max-w-full" />
        </div>
      </dl>
      <div className="flex gap-3 my-7">
        <Skeleton className="h-11 w-36 max-md:w-full" />
        <Skeleton className="h-11 w-36 max-md:hidden" />
      </div>
      <div className="pt-[18px] border-t border-border space-y-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-1.5 w-full mt-3" />
      </div>
    </div>
  )
}

export function StreakSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading study streak">
      <div className="my-8 mb-3 max-lg:mt-0 max-md:my-4">
        <Skeleton className="h-16 w-24 max-md:h-12" />
      </div>
      <div className="grid grid-cols-7 gap-2.5 my-7 max-lg:max-w-[320px] max-md:my-4 max-md:max-w-none max-md:gap-1.5">
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className="flex flex-col items-center gap-2.5">
            <Skeleton className="size-4 rounded-full" />
            <Skeleton className="h-3 w-3" />
          </div>
        ))}
      </div>
      <div className="border-t border-border pt-4.5 flex justify-between gap-3">
        <Skeleton className="h-4 w-28" />
        <Skeleton className="h-4 w-16" />
      </div>
    </div>
  )
}

export function HomeLibraryListSkeleton() {
  return (
    <div className="mt-3 space-y-2" role="status" aria-label="Loading library preview">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="grid grid-cols-[40px_minmax(0,1fr)_auto_20px] items-center gap-[18px] px-2 py-5 border-t border-border">
          <Skeleton className="size-8" />
          <div className="space-y-2 min-w-0">
            <Skeleton className="h-5 w-44 max-w-full" />
            <Skeleton className="h-3 w-28" />
          </div>
          <div className="flex items-center gap-4">
            <Skeleton className="h-4 w-16" />
            <Skeleton className="h-4 w-16" />
          </div>
          <Skeleton className="size-4" />
        </div>
      ))}
    </div>
  )
}

export function ActivitySkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading study activity">
      <div className="flex gap-6 mb-6">
        <Skeleton className="h-8 w-28" />
        <Skeleton className="h-8 w-36" />
      </div>
      <div className="grid gap-2 w-full max-w-[448px]">
        <div className="grid grid-cols-7 gap-2">
          {Array.from({ length: 7 }, (_, i) => (
            <Skeleton key={i} className="h-4 w-full" />
          ))}
        </div>
        <div className="grid grid-cols-7 gap-2">
          {Array.from({ length: 28 }, (_, i) => (
            <Skeleton key={i} className="aspect-square w-full" />
          ))}
        </div>
      </div>
    </div>
  )
}

export function ScheduleSkeleton() {
  return (
    <div className="space-y-6" role="status" aria-label="Loading review schedule">
      <div className="flex justify-between items-baseline gap-4 mb-4">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-20" />
      </div>
      <div className="grid grid-cols-4 gap-3 pt-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="flex flex-col items-center gap-2">
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-3 w-8" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function HomeDashboardSkeleton() {
  return (
    <div className="w-full animate-in fade-in duration-150" role="status" aria-label="Loading home dashboard">
      <HomeHeaderSkeleton />
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(260px,1fr)] border-b border-foreground [&_>_section]:min-w-0 [&_>_section]:p-6 [&_>_section:first-child]:pl-0 [&_>_section:first-child]:border-r [&_>_section:first-child]:border-border [&_>_section:last-child]:pr-0 max-xl:grid-cols-[minmax(0,1.5fr)_minmax(240px,1fr)] max-xl:[&_>_section]:p-5 max-lg:grid-cols-1 max-lg:[&_>_section]:py-6 max-lg:[&_>_section]:px-0 max-lg:[&_>_section:first-child]:border-r-0 max-lg:[&_>_section:first-child]:border-b max-lg:[&_>_section:first-child]:border-border">
        <section aria-label="Today">
          <div className="flex items-center justify-between gap-4 mb-6">
            <Skeleton className="h-7 w-28" />
            <Skeleton className="size-8" />
          </div>
          <TodaySkeleton />
        </section>
        <section aria-label="Study streak">
          <div className="flex items-center justify-between gap-4 mb-6">
            <Skeleton className="h-7 w-32" />
            <span className="size-3.5 rounded-full bg-art-red/40" />
          </div>
          <StreakSkeleton />
        </section>
      </div>
      <section className="py-8 border-b border-foreground" aria-label="From your library">
        <div className="flex items-center justify-between gap-4 mb-6">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-5 w-28" />
        </div>
        <div className="flex gap-2 mb-4">
          <Skeleton className="h-9 w-24" />
          <Skeleton className="h-9 w-24" />
        </div>
        <HomeLibraryListSkeleton />
      </section>
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(260px,1fr)] border-b border-border [&_>_section]:min-w-0 [&_>_section]:p-6 [&_>_section:first-child]:pl-0 [&_>_section:first-child]:border-r [&_>_section:first-child]:border-border [&_>_section:last-child]:pr-0 max-xl:grid-cols-[minmax(0,1.5fr)_minmax(240px,1fr)] max-xl:[&_>_section]:p-5 max-lg:grid-cols-1 max-lg:[&_>_section]:py-6 max-lg:[&_>_section]:px-0 max-lg:[&_>_section:first-child]:border-r-0 max-lg:[&_>_section:first-child]:border-b max-lg:[&_>_section:first-child]:border-border">
        <section aria-label="Study activity">
          <div className="flex items-center justify-between gap-4 mb-6">
            <Skeleton className="h-7 w-36" />
            <Skeleton className="h-4 w-28" />
          </div>
          <ActivitySkeleton />
        </section>
        <section aria-label="Review schedule">
          <div className="flex items-center justify-between gap-4 mb-6">
            <Skeleton className="h-7 w-36" />
          </div>
          <ScheduleSkeleton />
        </section>
      </div>
    </div>
  )
}
