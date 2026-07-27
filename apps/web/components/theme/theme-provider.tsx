"use client"

import { ThemeProvider as NextThemesProvider } from "next-themes"

/**
 * Theme root. `attribute="class"` is required: the whole token layer keys off
 * `.dark` (see the `@custom-variant dark` declaration in `app/globals.css`), so
 * the default `data-theme` attribute would leave every dark value unapplied.
 *
 * `disableTransitionOnChange` stops the one-frame colour crossfade that
 * otherwise runs on every element when the theme flips.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
    >
      {children}
    </NextThemesProvider>
  )
}
