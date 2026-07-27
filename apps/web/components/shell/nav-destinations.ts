import { BooksIcon, ChartLineUpIcon, HouseIcon, type Icon } from "@/lib/icons"

export interface NavDestination {
  href: string
  label: string
  icon: Icon
}

/**
 * Three destinations, and the list is the enforcement: the rail and the tab bar
 * both render from it, so a fourth cannot appear on one and not the other.
 *
 * A fourth destination is a design change, not an implementation detail. The
 * contextual surfaces — palette, activity, assistant — are deliberately not
 * here; they open over the current screen rather than replacing it.
 *
 * All three show for an anonymous visitor too. Hiding the two that need an
 * account would leave a one-item navigation bar that says nothing about what the
 * product does; the guard redirects to sign-in and returns them here afterwards.
 */
export const NAV_DESTINATIONS: readonly NavDestination[] = [
  { href: "/", label: "Today", icon: HouseIcon },
  { href: "/library", label: "Library", icon: BooksIcon },
  { href: "/progress", label: "Progress", icon: ChartLineUpIcon },
]

/**
 * Whether a destination is the current one. Nested paths keep their parent lit,
 * but `/` only matches itself: it is a prefix of everything.
 */
export function isCurrentDestination(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/"
  return pathname === href || pathname.startsWith(`${href}/`)
}
