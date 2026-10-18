import { Skeleton } from '@/components/ui/skeleton'
import { Motif } from '@/components/artwork/artwork'

export function DictionaryHeaderSkeleton() {
  return (
    <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border">
      <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0">
        <h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px]">
          Dictionary<span className="text-art-red">.</span>
        </h1>
      </div>
      <div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true">
        <Motif name="split-circle" />
      </div>
    </header>
  )
}

export function DictionarySearchSkeleton() {
  return (
    <div className="grid divide-y divide-border border-t border-border mt-2" role="status" aria-label="Searching dictionary">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="grid grid-cols-[30px_minmax(0,1fr)] items-center gap-3 w-full min-h-12 px-3 py-2">
          <Skeleton className="size-6" />
          <div className="space-y-1.5 min-w-0">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-48" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function WordDetailSkeleton() {
  return (
    <div className="grid grid-cols-[minmax(0,7fr)_minmax(230px,3fr)] border-b border-border max-[1000px]:grid-cols-1" role="status" aria-label="Loading word detail">
      <article className="min-w-0 pr-6.5 pt-6.5 pb-8 max-[1000px]:pr-0 space-y-6">
        <header className="flex justify-between gap-4 items-start pb-4 border-b border-border/50">
          <div className="space-y-2">
            <Skeleton className="h-12 w-48 max-w-full" />
            <Skeleton className="h-4 w-36" />
          </div>
          <Skeleton className="h-5 w-24" />
        </header>
        <div className="space-y-4">
          {Array.from({ length: 2 }, (_, i) => (
            <div key={i} className="grid grid-cols-[48px_minmax(0,1fr)_auto] gap-4 py-5 border-t border-border">
              <Skeleton className="h-6 w-8" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-6 w-3/4" />
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className="h-4 w-full" />
              </div>
              <Skeleton className="h-9 w-24" />
            </div>
          ))}
        </div>
      </article>
      <aside className="border-l border-border p-5.5 space-y-6 max-[1000px]:border-l-0 max-[1000px]:border-t">
        <div className="space-y-3">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="size-16 rounded-full" />
          <div className="grid grid-cols-3 gap-2">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        </div>
        <div className="space-y-3 pt-4 border-t border-border">
          <Skeleton className="h-5 w-28" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      </aside>
    </div>
  )
}

export function DictionaryPageSkeleton() {
  return (
    <div className="w-full min-w-0 animate-in fade-in duration-150" role="status" aria-label="Loading dictionary">
      <DictionaryHeaderSkeleton />
      <div className="flex items-center gap-3 border-b border-foreground min-h-[72px] px-3.5">
        <Skeleton className="size-5 shrink-0" />
        <Skeleton className="h-8 flex-1" />
        <Skeleton className="h-9 w-20" />
      </div>
      <div className="py-6">
        <DictionarySearchSkeleton />
      </div>
    </div>
  )
}
