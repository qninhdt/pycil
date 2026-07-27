"use client"

import * as React from "react"
import { useTheme } from "next-themes"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { DesktopIcon, MoonIcon, SunIcon } from "@/lib/icons"

const OPTIONS = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "System", icon: DesktopIcon },
] as const

/**
 * Three-way theme control. The stored preference is one of light/dark/system,
 * so a two-state switch cannot represent it: flipping a switch would silently
 * discard "follow the OS".
 *
 * The trigger renders the neutral desktop glyph until mounted. Before hydration
 * the resolved theme is unknown, and guessing produces a visible icon swap on
 * every load for anyone whose preference is not the default.
 */
export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => setMounted(true), [])

  const TriggerIcon = !mounted
    ? DesktopIcon
    : resolvedTheme === "dark"
      ? MoonIcon
      : SunIcon

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button variant="ghost" size="icon" aria-label="Change theme">
            <TriggerIcon />
          </Button>
        }
      />
      <DropdownMenuContent align="end">
        <DropdownMenuGroup>
          <DropdownMenuRadioGroup
            value={mounted ? theme : undefined}
            onValueChange={setTheme}
          >
            {OPTIONS.map(({ value, label, icon: Icon }) => (
              <DropdownMenuRadioItem key={value} value={value}>
                <Icon data-icon="inline-start" />
                {label}
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
