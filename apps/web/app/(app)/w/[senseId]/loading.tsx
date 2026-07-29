import { Skeleton } from "@/components/ui/skeleton"

/**
 * Placeholder for a sense record.
 *
 * Only the reading layer is sketched. The disclosure groups below it are closed on
 * arrival, so drawing placeholders for them would promise content the loaded page
 * does not show either.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-9 w-52" />
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-44" />
      </div>

      <div className="flex flex-col gap-3">
        <Skeleton className="h-5 w-full max-w-[65ch]" />
        <Skeleton className="h-5 w-3/4 max-w-[65ch]" />
        <Skeleton className="h-16 w-full max-w-[65ch]" />
      </div>

      <div className="flex flex-col gap-px">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-11 w-full" />
        ))}
      </div>
    </div>
  )
}
