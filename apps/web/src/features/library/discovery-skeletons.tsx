import { Motif } from '@/components/artwork/artwork'
import { Skeleton } from '@/components/ui/skeleton'

export function DiscoverySkeleton() {
  return (
    <div className="w-full min-w-0 animate-in fade-in duration-150" role="status" aria-label="Loading discovery">
      <header className="grid grid-cols-[minmax(0,3fr)_1fr] border-b border-border"><div className="py-6 pr-6 space-y-2">
        <h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold tracking-tight">
          Discovery<span className="text-art-red">.</span>
        </h1>
        <Skeleton className="h-4 w-80 max-w-full" />
      </div><div className="header-motif-art max-md:hidden" aria-hidden="true"><Motif name="split-circle" /></div></header>
      <div className="flex flex-wrap gap-3 py-4">
        <Skeleton className="h-10 w-72 max-w-full" />
        <Skeleton className="h-10 w-36" />
      </div>
      <ul className="grid grid-cols-3 gap-3 max-[1100px]:grid-cols-2 max-[650px]:grid-cols-1">
        {Array.from({ length: 6 }, (_, i) => (
          <li key={i} className="border border-border p-5 space-y-4 bg-background">
            <div className="flex items-start gap-3">
              <Skeleton className="size-7 shrink-0" />
              <div className="space-y-2 flex-1">
                <Skeleton className="h-5 w-3/4" />
                <Skeleton className="h-3 w-1/3" />
                <Skeleton className="h-4 w-full mt-2" />
              </div>
            </div>
            <div className="pt-2 border-t border-border/50 flex items-center gap-2">
              <Skeleton className="size-6 rounded-full" />
              <Skeleton className="h-3 w-24" />
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
