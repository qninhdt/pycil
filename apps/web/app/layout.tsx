import type { Metadata, Viewport } from "next"
import { Geist, Geist_Mono, Newsreader } from "next/font/google"

import { ThemeProvider } from "@/components/theme/theme-provider"
import { IconWeightProvider } from "@/components/theme/icon-weight-provider"
import { Toaster } from "@/components/ui/toast"

import "./globals.css"

/**
 * The three families the design system allows, and no more. Each is exposed as
 * a CSS variable rather than a class so the Tailwind `--font-*` theme entries in
 * `globals.css` can compose them into full stacks with fallbacks.
 *
 * Only the sans face is applied to `<html>`. Serif and mono are opt-in through
 * `font-serif` / `font-mono`, which is what keeps the "dictionary content is
 * serif, chrome is sans" rule enforceable by reading a component.
 */
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
})

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
})

/**
 * Lexicographic content only. 400 for definitions and examples, 600 for
 * headwords; no other weight is used, so no other weight is downloaded.
 */
const newsreader = Newsreader({
  variable: "--font-newsreader",
  subsets: ["latin"],
  weight: ["400", "600"],
  display: "swap",
})

export const metadata: Metadata = {
  title: {
    default: "Pycil",
    template: "%s · Pycil",
  },
  description:
    "A vocabulary trainer that schedules what you are about to forget.",
}

/**
 * `themeColor` follows the two canvas values so the mobile browser chrome
 * matches the page instead of framing it in white.
 */
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#FBFAF8" },
    { media: "(prefers-color-scheme: dark)", color: "#131211" },
  ],
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    // `suppressHydrationWarning` is required by next-themes: it writes the
    // resolved class onto <html> before React hydrates, so the server and
    // client markup differ by design on exactly this element.
    <html
      lang="en"
      suppressHydrationWarning
      className={`${geistSans.variable} ${geistMono.variable} ${newsreader.variable}`}
    >
      <body className="min-h-dvh bg-background text-foreground antialiased">
        <ThemeProvider>
          <IconWeightProvider>
            {children}
            <Toaster />
          </IconWeightProvider>
        </ThemeProvider>
      </body>
    </html>
  )
}
