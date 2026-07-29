"use client"

import { useState } from "react"

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible"
import { CaretDownIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

/**
 * One collapsed section of the sense record.
 *
 * Sense detail carries a dozen optional Lexi fields. Rendering them all open turns
 * the page into a field dump; dropping them throws away the work of phases 2 to 4.
 * So everything outside the reading layer lives in one of these, closed on arrival.
 *
 * A group with nothing in it renders nothing at all — not a heading with an empty
 * body, and not a disabled trigger. An absent field should leave no trace.
 */
export function DisclosureGroup({
  title,
  /** Rendered beside the title, e.g. how many items are inside. */
  hint,
  children,
  isEmpty,
}: {
  title: string
  hint?: string
  children: React.ReactNode
  /**
   * Whether the section has anything to show. Passed explicitly rather than
   * inferred from `children`, because a caller composing several fields knows
   * emptiness that React cannot see in an element tree.
   */
  isEmpty: boolean
}) {
  const [open, setOpen] = useState(false)

  if (isEmpty) return null

  return (
    <Collapsible open={open} onOpenChange={setOpen}>
      <CollapsibleTrigger className="group flex min-h-11 w-full items-center justify-between gap-3 border-b border-border text-left outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        <span className="flex items-baseline gap-2">
          <span className="text-sm font-medium">{title}</span>
          {hint ? (
            <span className="text-xs text-muted-foreground">{hint}</span>
          ) : null}
        </span>
        {/* Rotation is the only state signal, so it is on the icon rather than a
            swapped glyph: one element, no layout shift on toggle. Driven from the
            state this component already owns rather than from a panel data
            attribute, so it cannot silently stop working if the primitive renames
            one. */}
        <CaretDownIcon
          className={cn(
            "shrink-0 text-muted-foreground transition-transform duration-150",
            open && "rotate-180",
          )}
        />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="py-3">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  )
}
