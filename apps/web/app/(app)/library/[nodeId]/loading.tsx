import { Skeleton } from "@/components/ui/skeleton"

/**
 * Placeholder for a node view.
 *
 * Shaped for the header plus a list, which is what all three node kinds render.
 * Guessing per kind is not possible here: the loading boundary runs before the read
 * that would say whether this is a folder, a deck, or a reference.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-6">
      <Skeleton className="h-4 w-48" />

      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-40" />
      </div>

      <div className="flex flex-col gap-px">
        {Array.from({ length: 5 }, (_, index) => (
          <Skeleton key={index} className="h-16 w-full" />
        ))}
      </div>
    </div>
  )
}
