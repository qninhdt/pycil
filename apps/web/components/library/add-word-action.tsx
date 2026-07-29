"use client"

import { Button } from "@/components/ui/button"
import { MagnifyingGlassIcon } from "@/lib/icons"
import { useUiStore } from "@/lib/stores/store-provider"

/**
 * Opens the command palette scoped to this deck.
 *
 * Deliberately not a search surface of its own. The palette already debounces the
 * query, ranks results server-side, warns before an add that would end a live
 * session, and registers the resulting generation task with the activity store. A
 * second input next to the deck would have to reimplement all four, and the one it
 * would most likely omit is the session warning.
 */
export function AddWordAction({
  nodeId,
  className,
}: {
  nodeId: string
  className?: string
}) {
  const openPalette = useUiStore((state) => state.openPalette)

  return (
    <Button
      variant="outline"
      onClick={() => openPalette(nodeId)}
      className={className}
    >
      <MagnifyingGlassIcon data-icon="inline-start" />
      Add words
    </Button>
  )
}
