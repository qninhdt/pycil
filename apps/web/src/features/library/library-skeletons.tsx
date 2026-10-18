import { Skeleton } from '@/components/ui/skeleton'
import { Motif } from '@/components/artwork/artwork'

export function LibraryHeaderSkeleton({
  title,
}: {
  title?: string
}) {
  return (
    <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border">
      <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0 space-y-2">
        <div className="flex items-center gap-2 mb-1">
          <Skeleton className="h-3 w-16" />
          <span className="text-muted-foreground/30 text-xs">/</span>
          <Skeleton className="h-3 w-24" />
        </div>
        <div className="flex items-center gap-3">
          {title ? (
            <h1 className="text-[clamp(1.75rem,2.4vw,3rem)] font-extrabold leading-[1.15] tracking-[-.03em] max-[767px]:text-2xl">
              {title}<span className="text-art-red">.</span>
            </h1>
          ) : (
            <Skeleton className="h-10 w-52 max-w-full" />
          )}
          <Skeleton className="h-6 w-20" />
        </div>
        <Skeleton className="h-4 w-72 max-w-full mt-1" />
      </div>
      <div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true">
        <Motif name="split-circle" />
      </div>
    </header>
  )
}

export function LibrarySummarySkeleton() {
  return (
    <section className="library-summary grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 border-b border-border items-stretch" aria-label="Loading learning counts">
      <div className="min-w-0 py-4 pr-6 max-xl:pr-4 max-[767px]:pr-0 max-[767px]:border-b max-[767px]:border-border space-y-2">
        <div className="flex items-baseline gap-3">
          <Skeleton className="h-9 w-20" />
          <Skeleton className="h-4 w-12" />
        </div>
        <Skeleton className="h-1.5 w-full mt-3" />
      </div>
      <div className="border-l border-border py-4 pl-6 max-xl:pl-4 max-[767px]:hidden space-y-2">
        <Skeleton className="h-4 w-14" />
        <Skeleton className="h-7 w-12 mt-2" />
      </div>
      <div className="border-l border-border py-4 pl-6 max-xl:pl-4 max-[767px]:hidden space-y-2">
        <Skeleton className="h-4 w-14" />
        <Skeleton className="h-7 w-12 mt-2" />
      </div>
      <div className="border-l border-border py-4 pl-6 max-xl:pl-4 max-[767px]:hidden space-y-2">
        <Skeleton className="h-4 w-14" />
        <Skeleton className="h-7 w-12 mt-2" />
      </div>
    </section>
  )
}

export function LibraryToolbarSkeleton({ canCreate = true }: { canCreate?: boolean }) {
  return (
    <div className="flex justify-between items-center gap-4 mb-5 max-[767px]:items-stretch max-[767px]:flex-col">
      <Skeleton className="h-10 w-72 max-w-full" />
      <div className="flex items-center gap-2 flex-wrap">
        <Skeleton className="h-9 w-20" />
        {canCreate && (
          <>
            <Skeleton className="h-9 w-28 max-[767px]:flex-1" />
            <Skeleton className="h-9 w-28 max-[767px]:flex-1" />
          </>
        )}
      </div>
    </div>
  )
}

export function LibraryCardGridSkeleton({ count = 6 }: { count?: number }) {
  return (
    <ul className="grid grid-cols-3 gap-3 max-[1199px]:grid-cols-2 max-[767px]:grid-cols-1" role="status" aria-label="Loading library items">
      {Array.from({ length: count }, (_, i) => (
        <li key={i} className="min-h-[164px] border border-border p-4 flex flex-col justify-between bg-background">
          <div className="flex items-start gap-3">
            <Skeleton className="size-7 shrink-0" />
            <div className="space-y-2 flex-1 min-w-0">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          </div>
          <div className="flex items-center gap-4 pt-4 border-t border-border/50">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-3 w-16" />
          </div>
        </li>
      ))}
    </ul>
  )
}

export function LibraryTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="w-full border border-border" role="status" aria-label="Loading words table">
      <div className="grid grid-cols-[19%_52%_15%_14%] max-[767px]:hidden border-b border-border bg-muted/20 px-4 py-3">
        <Skeleton className="h-4 w-12" />
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-4 w-12" />
        <Skeleton className="h-4 w-24" />
      </div>
      <div className="divide-y divide-border">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className="grid grid-cols-[19%_52%_15%_14%] max-[767px]:grid-cols-1 gap-2 px-4 py-3.5 items-center">
            <div className="flex items-center gap-2">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-3 w-8" />
            </div>
            <Skeleton className="h-4 w-5/6" />
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-3 w-20" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function FlashcardSkeleton() {
  return (
    <div className="grid grid-cols-[40px_minmax(0,1fr)_40px] gap-3 items-center h-[420px] max-h-[420px]" role="status" aria-label="Loading flashcard">
      <Skeleton className="size-10" />
      <div className="h-full border border-foreground p-8 flex flex-col justify-between">
        <div className="space-y-4">
          <Skeleton className="h-4 w-20" />
          <Skeleton className="h-10 w-2/3" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
        <div className="pt-4 border-t border-border flex justify-between">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
        </div>
      </div>
      <Skeleton className="size-10" />
    </div>
  )
}

export function LibraryPageSkeleton({
  space = 'personal',
  title,
  showToolbar = true,
  publicRead = false,
  tab = 'overview',
  kind,
}: {
  space?: 'personal' | 'published'
  title?: string
  showToolbar?: boolean
  publicRead?: boolean
  tab?: 'overview' | 'words'
  kind?: 'folder' | 'deck'
}) {
  return (
    <div className="library-page w-full animate-in fade-in duration-150" role="status" aria-label="Loading library">
      <LibraryHeaderSkeleton title={title} />
      {!publicRead && <LibrarySummarySkeleton />}
      <div className="pt-4 space-y-4">
        <div className="flex gap-2 border-b border-border pb-2 mb-4">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
        </div>
        {showToolbar && kind !== 'deck' && <LibraryToolbarSkeleton canCreate={!publicRead && space === 'personal'} />}
        {tab === 'words' ? <LibraryTableSkeleton /> : kind === 'deck' ? <FlashcardSkeleton /> : kind === 'folder' ? <LibraryCardGridSkeleton count={6} /> : null}
      </div>
    </div>
  )
}
