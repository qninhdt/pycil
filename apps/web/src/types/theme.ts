export type ThemeMode = "light" | "dark" | "system";

export interface ThemeFonts {
  sans?: string | null; // Font name for sans-serif
  serif?: string | null; // Font name for serif
  mono?: string | null; // Font name for monospace
}

export interface ThemeDefinition {
  id: string;
  name: string;
  description?: string;
  className: string;
  fonts: ThemeFonts;
  primaryColor?: string; // Primary color for preview
}

export interface ThemeConfig {
  mode: ThemeMode;
  theme: string; // theme id
}

export const BUILT_IN_THEMES: ThemeDefinition[] = [
  {
    id: "default",
    name: "Default",
    description: "Clean and modern default theme",
    className: "theme-default",
    fonts: {
      sans: null,
      serif: null,
      mono: null,
    },
    primaryColor: "oklch(0.205 0 0)",
  },
  {
    id: "art-deco",
    name: "Art Deco",
    description: "Nature-inspired green theme",
    className: "theme-art-deco",
    fonts: {
      sans: "Delius Swash Caps",
      serif: "Delius Swash Caps",
      mono: "Delius Swash Caps",
    },
    primaryColor: "oklch(0.77 0.14 91.27)",
  },
  {
    id: "modern-minimal",
    name: "Modern Minimal",
    description: "Sleek and simple monochrome theme",
    className: "theme-modern-minimal",
    fonts: {
      sans: null,
      serif: "Source Serif 4",
      mono: "JetBrains Mono",
    },
    primaryColor: "oklch(0.62 0.19 259.76)",
  },
  {
    id: "neo-brutalism",
    name: "Neo Brutalism",
    description: "Bold and striking high-contrast theme",
    className: "theme-neo-brutalism",
    fonts: {
      sans: "DM Sans",
      serif: null,
      mono: "Space Mono",
    },
    primaryColor: "oklch(0.65 0.24 26.92)",
  },
  {
    id: "ghibli-studio",
    name: "Ghibli Studio",
    description: "Warm and nostalgic theme",
    className: "theme-ghibli-studio",
    fonts: {
      sans: "Nunito",
      serif: "PT Serif",
      mono: "JetBrains Mono",
    },
    primaryColor: "oklch(0.71 0.1 111.96)",
  },
  {
    id: "pastel-dream",
    name: "Pastel Dream",
    description: "Soft and calming pastel theme",
    className: "theme-pastel-dream",
    fonts: {
      sans: "Open Sans",
      serif: "Source Serif 4",
      mono: "IBM Plex Mono",
    },
    primaryColor: "oklch(0.71 0.16 293.4)",
  },
];
