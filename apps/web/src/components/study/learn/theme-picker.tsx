"use client";

import { cn } from "@/lib/utils";
import { themeList } from "@/lib/questions/themes";

interface ThemePickerProps {
  value: string | null;
  onChange: (themeId: string) => void;
  className?: string;
}

/** Theme selection shown at learning-session start. Presentation only. */
export function ThemePicker({ value, onChange, className }: ThemePickerProps) {
  return (
    <div className={cn("space-y-2", className)}>
      <p className="text-sm font-medium text-muted-foreground">Choose a theme</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {themeList().map((theme) => (
          <button
            key={theme.id}
            type="button"
            onClick={() => onChange(theme.id)}
            className={cn(
              "rounded-lg border-2 p-3 text-sm transition-all",
              theme.cardClass,
              value === theme.id
                ? "ring-2 ring-primary"
                : "opacity-80 hover:opacity-100"
            )}
          >
            <span className={cn("font-medium", theme.accentClass)}>
              {theme.name}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
