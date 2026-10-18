import { Skeleton } from '@/components/ui/skeleton'
import { Shape } from '@/components/artwork/artwork'
import { LibraryCardGridSkeleton } from '@/features/library/library-skeletons'

export function PublicProfileSkeleton() {
  return <div className="w-full space-y-8" role="status" aria-label="Loading profile">
    <header className="grid min-h-[204px] grid-cols-[160px_minmax(0,1fr)] gap-7 border border-border max-sm:grid-cols-[90px_minmax(0,1fr)] max-sm:gap-3.5">
      <div className="grid place-items-center border-r border-border" aria-hidden="true"><Shape name="circle" className="size-20 max-sm:size-14" /></div>
      <div className="self-center space-y-3 py-6 pr-4"><Skeleton className="h-10 w-60 max-w-full" /><Skeleton className="h-5 w-32" /><Skeleton className="h-4 w-96 max-w-full" /><Skeleton className="h-3 w-36" /></div>
    </header>
    <Skeleton className="h-7 w-56" />
    <LibraryCardGridSkeleton />
  </div>
}
