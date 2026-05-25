import {
  Geist,
  Delius_Swash_Caps,
  DM_Sans,
  Space_Mono,
  Source_Serif_4,
  JetBrains_Mono,
  Nunito,
  PT_Serif,
  Open_Sans,
  IBM_Plex_Mono,
} from "next/font/google";

// Define Google Fonts with optimized settings
const geist = Geist({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const geistMono = Geist({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

const deliusSwashCaps = Delius_Swash_Caps({
  subsets: ["latin"],
  weight: ["400"],
  variable: "--font-serif",
  display: "swap",
});

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
});

const spaceMono = Space_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-space-mono",
  display: "swap",
});

const sourceSerif4 = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif-4",
  display: "swap",
});

const jetBrainMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

const nunito = Nunito({
  subsets: ["latin"],
  variable: "--font-nunito",
  display: "swap",
});

const ptSerif = PT_Serif({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-pt-serif",
  display: "swap",
});

const openSans = Open_Sans({
  subsets: ["latin"],
  variable: "--font-open-sans",
  display: "swap",
});

const ibmPlexSans = IBM_Plex_Mono({
  weight: ["400", "700"],
  subsets: ["latin"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

// Font mapping with better typing
export const FONT_MAP = {
  Geist: geist.variable,
  "Geist Mono": geistMono.variable,
  "Delius Swash Caps": deliusSwashCaps.variable,
  "DM Sans": dmSans.variable,
  "Space Mono": spaceMono.variable,
  "Source Serif 4": sourceSerif4.variable,
  "JetBrains Mono": jetBrainMono.variable,
  Nunito: nunito.variable,
  "PT Serif": ptSerif.variable,
  "Open Sans": openSans.variable,
  "IBM Plex Mono": ibmPlexSans.variable,
} as const;

export type FontName = keyof typeof FONT_MAP;
