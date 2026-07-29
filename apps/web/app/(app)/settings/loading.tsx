import { Skeleton } from "@/components/ui/skeleton"

/**
 * Placeholder for the settings screen.
 *
 * Shaped as a title plus a stack of cards, which is what every section renders. The deck
 * defaults section has an unknown height before the read, so it gets one card's worth
 * rather than a guess per deck: a skeleton taller than the content costs a second layout
 * shift when it lands.
 */
export default function Loading() {
  return (
    <div className="flex flex-col gap-8 lg:gap-12">
      <Skeleton className="h-8 w-32" />

      {Array.from({ length: 4 }, (_, index) => (
        <Skeleton key={index} className="h-32 w-full" />
      ))}
    </div>
  )
}
