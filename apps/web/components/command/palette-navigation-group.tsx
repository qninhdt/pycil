"use client"

import { useRouter } from "next/navigation"

import { CommandGroup, CommandItem } from "@/components/ui/command"
import { GearIcon } from "@/lib/icons"

import { NAV_DESTINATIONS } from "@/components/shell/nav-destinations"

/** The palette's jump targets: the three destinations, plus settings. */
const TARGETS = [
  ...NAV_DESTINATIONS.map(({ href, label, icon }) => ({ href, label, icon })),
  // Reachable from the avatar menu, and the one screen people reach for in a
  // palette by habit. It is not a fourth destination: it has no nav entry.
  { href: "/settings", label: "Settings", icon: GearIcon },
]

/**
 * Jumping to a screen from the palette, read from the same destination list the
 * rail and the tab bar use so a fourth entry cannot appear in only one of them.
 *
 * Filtering happens here rather than in cmdk. The palette runs with
 * `shouldFilter={false}` because word results are ranked by the API and
 * re-filtering them client-side drops legitimate hits, so every group that does
 * want filtering has to do its own.
 */
export function PaletteNavigationGroup({
  query,
  onNavigate,
}: {
  query: string
  onNavigate: () => void
}) {
  const router = useRouter()
  const needle = query.trim().toLowerCase()
  const matches = needle
    ? TARGETS.filter((target) => target.label.toLowerCase().includes(needle))
    : TARGETS

  if (matches.length === 0) return null

  const go = (href: string) => {
    onNavigate()
    router.push(href)
  }

  return (
    <CommandGroup heading="Go to">
      {matches.map(({ href, label, icon: Icon }) => (
        <CommandItem key={href} value={`go ${label}`} onSelect={() => go(href)}>
          <Icon />
          {label}
        </CommandItem>
      ))}
    </CommandGroup>
  )
}
