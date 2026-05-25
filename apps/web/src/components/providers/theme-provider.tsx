"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useCallback,
} from "react";
import { cn } from "@/lib/utils";
import { ThemeProvider as NextThemeProvider } from "next-themes";
import { BUILT_IN_THEMES, type ThemeDefinition } from "@/types/theme";
import { useLocalStorage } from "@/hooks/use-local-storage";
import { FONT_MAP, type FontName } from "@/lib/fonts";

// Constants
const DEFAULT_THEME_ID = "default";
const THEME_STORAGE_KEY = "app-custom-theme";
const FONT_TYPE_STORAGE_KEY = "app-font-type";

// Font type options
export type FontType = "sans" | "serif" | "mono";
const DEFAULT_FONT_TYPE: FontType = "sans";

// Helper function to get font classes from theme
const getFontClasses = (theme: ThemeDefinition | undefined): string => {
  if (!theme?.fonts) return "";

  const fontClasses = Object.values(theme.fonts)
    .filter((font): font is FontName => Boolean(font && font in FONT_MAP))
    .map((font) => FONT_MAP[font])
    .join(" ");

  return fontClasses;
};

// Helper function to get the appropriate Tailwind font class
const getFontTypeClass = (fontType: FontType): string => {
  switch (fontType) {
    case "sans":
      return "font-sans";
    case "serif":
      return "font-serif";
    case "mono":
      return "font-mono";
    default:
      return "font-sans";
  }
};

interface CustomThemeContextType {
  currentTheme: string;
  setTheme: (themeId: string) => void;
  availableThemes: ThemeDefinition[];
  isLoaded: boolean;
  fontType: FontType;
  setFontType: (fontType: FontType) => void;
}

const CustomThemeContext = createContext<CustomThemeContextType | undefined>(
  undefined
);

interface CustomThemeProviderProps {
  children: React.ReactNode;
}

const CustomThemeProvider = ({ children }: CustomThemeProviderProps) => {
  const [currentTheme, setCurrentTheme, isLoaded] = useLocalStorage(
    THEME_STORAGE_KEY,
    DEFAULT_THEME_ID
  );

  const [fontType, setFontType] = useLocalStorage<FontType>(
    FONT_TYPE_STORAGE_KEY,
    DEFAULT_FONT_TYPE
  );

  const availableThemes = useMemo(() => BUILT_IN_THEMES, []);

  const currentThemeDefinition = useMemo(
    () => availableThemes.find((theme) => theme.id === currentTheme),
    [availableThemes, currentTheme]
  );

  // Apply theme class to document root
  useEffect(() => {
    if (!isLoaded) return;

    const root = document.documentElement;

    // Remove all theme classes
    availableThemes.forEach((theme) => {
      root.classList.remove(theme.className);
    });

    // Apply current theme class
    if (currentThemeDefinition) {
      root.classList.add(currentThemeDefinition.className);
    }
  }, [currentTheme, availableThemes, currentThemeDefinition, isLoaded]);

  const handleSetTheme = useCallback(
    (themeId: string) => {
      const themeExists = availableThemes.some((theme) => theme.id === themeId);
      if (!themeExists) {
        console.warn(
          `Theme "${themeId}" not found. Available themes:`,
          availableThemes.map((t) => t.id)
        );
        return;
      }
      setCurrentTheme(themeId);
    },
    [availableThemes, setCurrentTheme]
  );

  const handleSetFontType = useCallback(
    (newFontType: FontType) => {
      setFontType(newFontType);
    },
    [setFontType]
  );

  const contextValue = useMemo<CustomThemeContextType>(
    () => ({
      currentTheme,
      setTheme: handleSetTheme,
      availableThemes,
      isLoaded,
      fontType,
      setFontType: handleSetFontType,
    }),
    [
      currentTheme,
      handleSetTheme,
      availableThemes,
      isLoaded,
      fontType,
      handleSetFontType,
    ]
  );

  const allFontClasses = useMemo(
    () => getFontClasses(currentThemeDefinition),
    [currentThemeDefinition]
  );

  const fontTypeClass = useMemo(() => getFontTypeClass(fontType), [fontType]);

  return (
    <CustomThemeContext.Provider value={contextValue}>
      <div className={cn(allFontClasses, fontTypeClass, "antialiased")}>
        {children}
      </div>
    </CustomThemeContext.Provider>
  );
};

interface ThemeProviderProps {
  children: React.ReactNode;
}

export const ThemeProvider = ({ children }: ThemeProviderProps) => {
  return (
    <NextThemeProvider
      attribute="class"
      defaultTheme="system"
      storageKey="app-theme-mode"
      enableSystem
      disableTransitionOnChange
    >
      <CustomThemeProvider>{children}</CustomThemeProvider>
    </NextThemeProvider>
  );
};

export const useCustomTheme = () => {
  const context = useContext(CustomThemeContext);
  if (context === undefined) {
    throw new Error("useCustomTheme must be used within a CustomThemeProvider");
  }
  return context;
};
