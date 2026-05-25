"use client";

import React, { memo, useMemo, useCallback } from "react";
import { signOut } from "next-auth/react";
import { useQueryClient } from "@tanstack/react-query";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  AdaptiveMenu,
  AdaptiveMenuContent,
  AdaptiveMenuItem,
  AdaptiveMenuLabel,
  AdaptiveMenuSeparator,
  AdaptiveMenuSub,
  AdaptiveMenuSubContent,
  AdaptiveMenuSubTrigger,
} from "@/components/ui/adaptive-menu";
import { useMe } from "@/lib/api-hooks/use-auth";
import { useTheme } from "next-themes";
import { useCustomTheme } from "@/components/providers/theme-provider";
import type { FontType } from "@/components/providers/theme-provider";
import {
  User,
  Settings,
  Sun,
  Moon,
  LogOut,
  Monitor,
  Palette,
  Check,
  Type,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";

// --- Type Definitions ---
interface ThemeOption {
  readonly value: "light" | "dark" | "system";
  readonly icon: LucideIcon;
  readonly label: string;
}

interface FontOption {
  readonly value: FontType;
  readonly label: string;
}

// --- Constants ---
const THEME_OPTIONS: readonly ThemeOption[] = [
  { value: "light", icon: Sun, label: "Light Mode" },
  { value: "dark", icon: Moon, label: "Dark Mode" },
  { value: "system", icon: Monitor, label: "System Mode" },
] as const;

const FONT_OPTIONS: readonly FontOption[] = [
  { value: "sans", label: "Sans Serif" },
  { value: "serif", label: "Serif" },
  { value: "mono", label: "Monospace" },
] as const;

// --- Optimized Sub-components ---

/**
 * Memoized theme settings component
 */
const ThemeSettings = memo(() => {
  const { theme: currentMode, setTheme: setMode } = useTheme();
  const {
    currentTheme,
    setTheme: setCustomTheme,
    availableThemes,
  } = useCustomTheme();

  const handleModeChange = useCallback(
    (newMode: "light" | "dark" | "system") => {
      setMode(newMode);
    },
    [setMode]
  );

  const handleThemeChange = useCallback(
    (themeId: string) => {
      setCustomTheme(themeId);
    },
    [setCustomTheme]
  );

  return (
    <>
      <AdaptiveMenuLabel>Appearance Mode</AdaptiveMenuLabel>
      {THEME_OPTIONS.map((theme) => (
        <AdaptiveMenuItem
          key={theme.value}
          onSelect={() => handleModeChange(theme.value)}
        >
          <theme.icon className="mr-2 h-4 w-4" aria-hidden="true" />
          <span>{theme.label}</span>
          {currentMode === theme.value && (
            <Check className="ml-auto h-4 w-4" aria-hidden="true" />
          )}
        </AdaptiveMenuItem>
      ))}

      <AdaptiveMenuSeparator />

      <AdaptiveMenuLabel>Color Theme</AdaptiveMenuLabel>
      {availableThemes.map((theme) => (
        <AdaptiveMenuItem
          key={theme.id}
          onSelect={() => handleThemeChange(theme.id)}
        >
          <div className="flex items-center w-full">
            {theme.primaryColor && (
              <div
                className="mr-2 h-4 w-4 rounded-full border-2 border-border"
                style={{ backgroundColor: theme.primaryColor }}
                aria-hidden="true"
              />
            )}
            <span>{theme.name}</span>
            {currentTheme === theme.id && (
              <Check className="ml-auto h-4 w-4" aria-hidden="true" />
            )}
          </div>
        </AdaptiveMenuItem>
      ))}
    </>
  );
});

ThemeSettings.displayName = "ThemeSettings";

/**
 * Memoized font settings component
 */
const FontSettings = memo(() => {
  const { fontType, setFontType } = useCustomTheme();

  const handleFontChange = useCallback(
    (newFontType: FontType) => {
      setFontType(newFontType);
    },
    [setFontType]
  );

  return (
    <>
      <AdaptiveMenuLabel>Font Type</AdaptiveMenuLabel>
      {FONT_OPTIONS.map((font) => (
        <AdaptiveMenuItem
          key={font.value}
          onSelect={() => handleFontChange(font.value)}
        >
          <Type className="mr-2 h-4 w-4" aria-hidden="true" />
          <span>{font.label}</span>
          {fontType === font.value && (
            <Check className="ml-auto h-4 w-4" aria-hidden="true" />
          )}
        </AdaptiveMenuItem>
      ))}
    </>
  );
});

FontSettings.displayName = "FontSettings";

/**
 * Memoized user avatar component
 */
const UserAvatar = memo(() => {
  const { data: me } = useMe();

  const userInitials = useMemo(() => {
    const source = me?.name?.trim() || me?.email.split("@")[0] || "";
    return (
      source
        .split(/\s+/)
        .map((n) => n[0])
        .filter(Boolean)
        .slice(0, 2)
        .join("")
        .toUpperCase() || "?"
    );
  }, [me]);

  const displayName = me?.name?.trim() || me?.email || "Account";

  return (
    <Avatar className="h-10 w-10">
      {me?.image && (
        <AvatarImage src={me.image} alt={`${displayName} avatar`} />
      )}
      <AvatarFallback>{userInitials}</AvatarFallback>
    </Avatar>
  );
});

UserAvatar.displayName = "UserAvatar";

/**
 * Optimized main user dropdown component
 */
export const UserDropdown = memo(() => {
  const [open, setOpen] = React.useState(false);
  const { data: me } = useMe();
  const qc = useQueryClient();

  const handleOpenChange = useCallback((newOpen: boolean) => {
    setOpen(newOpen);
  }, []);

  const handleMenuItemSelect = useCallback(() => {
    setOpen(false);
  }, []);

  const handleSignOut = useCallback(async () => {
    setOpen(false);
    qc.clear();
    await signOut({ callbackUrl: "/sign-in" });
  }, [qc]);

  const triggerButton = useMemo(
    () => (
      <Button
        variant="ghost"
        className="relative h-10 w-10 rounded-full"
        aria-label="User menu"
        aria-expanded={open}
        aria-haspopup="true"
      >
        <UserAvatar />
      </Button>
    ),
    [open]
  );

  return (
    <AdaptiveMenu
      open={open}
      onOpenChange={handleOpenChange}
      title="Account"
      trigger={triggerButton}
    >
      <AdaptiveMenuContent align="end">
        <AdaptiveMenuLabel>
          <div className="flex flex-col space-y-1">
            <p className="text-sm font-medium leading-none">
              {me?.name?.trim() || me?.email?.split("@")[0] || "Account"}
            </p>
            {me?.email && (
              <p className="text-xs leading-none text-muted-foreground">
                {me.email}
              </p>
            )}
          </div>
        </AdaptiveMenuLabel>
        <AdaptiveMenuSeparator />

        <AdaptiveMenuItem onSelect={handleMenuItemSelect}>
          <Link href="/profile" className="flex w-full items-center">
            <User className="mr-2 h-4 w-4" aria-hidden="true" />
            Profile
          </Link>
        </AdaptiveMenuItem>

        <AdaptiveMenuItem onSelect={handleMenuItemSelect}>
          <Link href="/settings" className="flex w-full items-center">
            <Settings className="mr-2 h-4 w-4" aria-hidden="true" />
            Settings
          </Link>
        </AdaptiveMenuItem>

        <AdaptiveMenuSeparator />

        <AdaptiveMenuSub title="Theme">
          <AdaptiveMenuSubTrigger>
            <Palette className="mr-2 h-4 w-4" aria-hidden="true" />
            <span>Appearance</span>
          </AdaptiveMenuSubTrigger>
          <AdaptiveMenuSubContent>
            <ThemeSettings />
            <AdaptiveMenuSeparator />
            <FontSettings />
          </AdaptiveMenuSubContent>
        </AdaptiveMenuSub>

        <AdaptiveMenuSeparator />

        <AdaptiveMenuItem variant="destructive" onSelect={handleSignOut}>
          <LogOut className="mr-2 h-4 w-4" aria-hidden="true" />
          <span>Log out</span>
        </AdaptiveMenuItem>
      </AdaptiveMenuContent>
    </AdaptiveMenu>
  );
});

UserDropdown.displayName = "UserDropdown";
