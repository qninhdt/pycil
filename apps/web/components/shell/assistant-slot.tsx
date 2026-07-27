"use client"

import { Button } from "@/components/ui/button"
import { SparkleIcon } from "@/lib/icons"
import { useUiStore } from "@/lib/stores/store-provider"

/**
 * The assistant seam. This renders the trigger only; the surface itself lands
 * in a later phase and reads `openSurface === "assistant"` from the same store.
 *
 * When the capability is off the whole thing is *absent*, not disabled. A
 * disabled control tells a learner the product has a feature they cannot use,
 * which is worse than saying nothing: the capability is off because the
 * deployment has no assistant, not because of anything about them.
 */
export function AssistantTrigger({ enabled }: { enabled: boolean }) {
  const toggleAssistant = useUiStore((state) => state.toggleAssistant)
  const openSurface = useUiStore((state) => state.openSurface)

  if (!enabled) return null

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Assistant"
      aria-expanded={openSurface === "assistant"}
      onClick={toggleAssistant}
    >
      <SparkleIcon />
    </Button>
  )
}
