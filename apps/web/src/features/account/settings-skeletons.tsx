import { Skeleton } from '@/components/ui/skeleton'
import { Shape } from '@/components/artwork/artwork'

export function SettingsSkeleton() {
  return (
    <div className="w-full animate-in fade-in duration-150" role="status" aria-label="Loading settings">
      <header className="grid grid-cols-[minmax(0,1.3fr)_1fr_1fr_1fr] max-[767px]:grid-cols-1 items-stretch min-h-[124px] max-[767px]:min-h-0 max-[767px]:py-4 border-b border-border">
        <div className="col-span-3 max-[767px]:col-span-1 min-w-0 flex flex-col justify-center py-4 pr-6 max-[767px]:p-0">
          <h1 className="text-[clamp(2.25rem,2.6vw,3rem)] font-extrabold leading-[1.12] tracking-[-.03em] max-[700px]:text-[34px]">
            Settings<span className="text-art-red">.</span>
          </h1>
        </div>
        <div className="header-motif-art col-span-1 max-[767px]:hidden" aria-hidden="true">
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 flex items-center justify-center [&_svg:first-child]:size-[112px] [&_svg:last-child]:-ml-7 [&_svg:last-child]:size-[90px] [&_svg:last-child]:translate-y-[32px]">
            <Shape name="square" />
            <Shape name="triangle" />
          </div>
        </div>
      </header>
      <div className="py-6 space-y-6 max-w-[640px]">
        <div className="flex gap-2 border-b border-border pb-2 mb-6">
          <Skeleton className="h-8 w-24" />
          <Skeleton className="h-8 w-24" />
        </div>
        <div className="space-y-4">
          <div className="space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-10 w-full" />
          </div>
          <div className="space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-10 w-full" />
          </div>
          <div className="space-y-2">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-10 w-full" />
          </div>
          <Skeleton className="h-10 w-32 mt-4" />
        </div>
      </div>
    </div>
  )
}
