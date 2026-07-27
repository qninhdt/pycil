import { Skeleton } from "@/components/ui/skeleton"

/**
 * The shell renders immediately and only the content column waits, so this
 * placeholder mirrors the shape of a page rather than covering the screen.
 *
 * Heights match the real blocks. A skeleton of the wrong size costs a second
 * layout shift when the content lands, which is worse than no skeleton.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-28 w-full" />
      </div>
      <Skeleton className="h-24 w-full" />
      <div className="flex flex-col gap-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  )
}
