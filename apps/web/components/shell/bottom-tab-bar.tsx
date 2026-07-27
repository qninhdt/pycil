"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { LAYER_CLASS } from "@/lib/design/layers"
import { cn } from "@/lib/utils"

import { isCurrentDestination, NAV_DESTINATIONS } from "./nav-destinations"

/**
 * Mobile and tablet navigation. Hidden from `lg` up by a class, not by a
 * breakpoint hook: a hook would render the wrong bar on the server and swap it
 * after hydration, which is a visible flash on every cold load.
 *
 * `aria-hidden` is deliberately not used on the hidden one — `display: none`
 * already removes it from the accessibility tree, and at most one of the two is
 * ever displayed.
 */
export function BottomTabBar() {
  const pathname = usePathname()

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "fixed inset-x-0 bottom-0 border-t border-border bg-background lg:hidden",
        LAYER_CLASS.bottomNav,
        // The iOS home indicator overlaps a bar that only pads to its own edge.
        "pb-[env(safe-area-inset-bottom)]",
      )}
    >
      <ul className="flex items-stretch">
        {NAV_DESTINATIONS.map((destination) => {
          const current = isCurrentDestination(pathname, destination.href)
          const Icon = destination.icon
          return (
            <li key={destination.href} className="flex-1">
              <Link
                href={destination.href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  // 44px is the floor for a touch target; the label pushes it
                  // taller, so min-h states the guarantee rather than the size.
                  "flex min-h-11 flex-col items-center justify-center gap-0.5 px-2 py-2 text-xs",
                  "outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  current ? "text-foreground" : "text-muted-foreground",
                )}
              >
                {/* Only the current item overrides the house weight. Passing
                    `regular` to the others would make them thinner than every
                    other icon on the screen. */}
                <Icon className="size-5" weight={current ? "fill" : undefined} />
                {destination.label}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
