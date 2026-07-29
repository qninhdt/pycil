import { Skeleton } from "@/components/ui/skeleton"

/**
 * Placeholder for the root listing.
 *
 * The row heights match `NodeRow`, so the content landing does not shift the page.
 * A skeleton of the wrong size costs a second layout shift, which is worse than
 * showing nothing.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <Skeleton className="h-8 w-32" />
        <Skeleton className="h-7 w-20" />
      </div>

      <div className="flex flex-col gap-px">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    </div>
  )
}
