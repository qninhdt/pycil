"use client"

/**
 * The assistant's trigger in the header.
 *
 * Only the trigger. The surface it opens is mounted by `AppShell`, because the
 * desktop rendering is an in-flow column that has to be a sibling of `<main>` to
 * take width from it. Hanging it here instead looked tidier and did not work: the
 * header carries a `backdrop-filter`, which makes it the containing block for any
 * fixed descendant, and a `z-index`, which traps that descendant in its stacking
 * context — so the sidebar came out zero-height and painted under the tab bar.
 *
 * The two halves talk through the store rather than through props, which is what
 * lets them sit in different parts of the tree.
 */

import { Button } from "@/components/ui/button"
import { SparkleIcon } from "@/lib/icons"
import { useUiStore } from "@/lib/stores/store-provider"

/**
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
