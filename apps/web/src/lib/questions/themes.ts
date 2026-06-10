/**
 * Frontend theme catalog. Mirrors the backend theme ids
 * (pycil_core/services/theme_service.py) and maps each to a visual skin.
 * Presentation only — themes never affect grading. Adding a theme = a catalog
 * entry here + the matching backend entry.
 */
export interface ThemeSkin {
  id: string;
  name: string;
  /** Tailwind classes applied to the question card for this theme. */
  cardClass: string;
  /** Accent class for headings/CTAs. */
  accentClass: string;
}

export const THEME_SKINS: Record<string, ThemeSkin> = {
  classic: {
    id: "classic",
    name: "Classic",
    cardClass: "bg-card border-border",
    accentClass: "text-foreground",
  },
  space: {
    id: "space",
    name: "Space Explorer",
    cardClass: "bg-indigo-950/40 border-indigo-500/40",
    accentClass: "text-indigo-300",
  },
  ocean: {
    id: "ocean",
    name: "Deep Ocean",
    cardClass: "bg-cyan-950/40 border-cyan-500/40",
    accentClass: "text-cyan-300",
  },
  fantasy: {
    id: "fantasy",
    name: "Fantasy Quest",
    cardClass: "bg-amber-950/30 border-amber-500/40",
    accentClass: "text-amber-300",
  },
};

export const DEFAULT_THEME_ID = "classic";

export function themeSkin(themeId: string | null | undefined): ThemeSkin {
  if (!themeId) return THEME_SKINS[DEFAULT_THEME_ID];
  return THEME_SKINS[themeId] ?? THEME_SKINS[DEFAULT_THEME_ID];
}

export function themeList(): ThemeSkin[] {
  return Object.values(THEME_SKINS);
}
