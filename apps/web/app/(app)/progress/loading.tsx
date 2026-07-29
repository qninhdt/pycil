import { Skeleton } from "@/components/ui/skeleton"

/**
 * Placeholder for the Progress screen.
 *
 * Shaped for the figure row, the ramp, and two chart blocks, which is what this page
 * renders whenever there is any data at all. Heights match the real blocks so the
 * content landing does not shift the layout a second time.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <div className="flex flex-col gap-4">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-9 w-full sm:w-64" />
      </div>

      <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>

      <div className="flex flex-col gap-3">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-10 w-full" />
      </div>

      <div className="flex flex-col gap-3">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="aspect-[2/1] w-full" />
      </div>
    </div>
  )
}
