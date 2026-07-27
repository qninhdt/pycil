"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"

import { LAYER_CLASS } from "@/lib/design/layers"
import { cn } from "@/lib/utils"

import { isCurrentDestination, NAV_DESTINATIONS } from "./nav-destinations"

/**
 * Desktop navigation, 224px fixed. Appears from `lg` up by class, mirroring the
 * tab bar's `lg:hidden`, so exactly one of the two is displayed at any width and
 * neither depends on JavaScript to decide.
 */
export function NavRail() {
  const pathname = usePathname()

  return (
    <nav
      aria-label="Primary"
      className={cn(
        "fixed inset-y-0 left-0 hidden w-56 flex-col border-r border-border bg-background lg:flex",
        LAYER_CLASS.bottomNav,
      )}
    >
      <Link
        href="/"
        className="flex h-14 items-center px-5 font-serif text-lg font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
      >
        Pycil
      </Link>

      <ul className="flex flex-col gap-1 px-3 py-2">
        {NAV_DESTINATIONS.map((destination) => {
          const current = isCurrentDestination(pathname, destination.href)
          const Icon = destination.icon
          return (
            <li key={destination.href}>
              <Link
                href={destination.href}
                aria-current={current ? "page" : undefined}
                className={cn(
                  "flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm",
                  "outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                  current
                    ? "bg-wash-primary font-medium text-on-wash-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground",
                )}
              >
                {/* Only the current item overrides the house weight. Passing
                    `regular` for the rest would make navigation icons thinner
                    than every other icon on the same screen. */}
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
