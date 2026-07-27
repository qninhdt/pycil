"use client"

import { IconContext } from "@/lib/icons"

/**
 * Sets the Phosphor weight and default size once for the whole tree. Without a
 * single provider the weight is passed per call site and drifts, which shows up
 * as mismatched stroke thickness between two icons sitting next to each other.
 *
 * `bold` is the design system's choice: it matches the slightly technical
 * stroke the interface wants without reading as a filled glyph.
 */
export function IconWeightProvider({ children }: { children: React.ReactNode }) {
  return (
    <IconContext.Provider value={{ weight: "bold", size: "1em" }}>
      {children}
    </IconContext.Provider>
  )
}
