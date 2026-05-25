"use client";

import { useTheme } from "next-themes";
import { useCustomTheme } from "@/components/providers/theme-provider";
import type { FontType } from "@/components/providers/theme-provider";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Sun, Moon, Monitor, Check } from "lucide-react";

const MODES = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
] as const;

const FONTS: { value: FontType; label: string }[] = [
  { value: "sans", label: "Sans Serif" },
  { value: "serif", label: "Serif" },
  { value: "mono", label: "Monospace" },
];

export function ThemeSection() {
  const { theme, setTheme } = useTheme();
  const {
    currentTheme,
    setTheme: setCustomTheme,
    availableThemes,
    fontType,
    setFontType,
  } = useCustomTheme();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <p className="text-sm font-medium">Mode</p>
          <div className="flex flex-wrap gap-2">
            {MODES.map((m) => {
              const active = theme === m.value;
              return (
                <Button
                  key={m.value}
                  variant={active ? "default" : "outline"}
                  size="sm"
                  onClick={() => setTheme(m.value)}
                >
                  <m.icon className="h-4 w-4 mr-2" />
                  {m.label}
                  {active && <Check className="h-4 w-4 ml-2" />}
                </Button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Color theme</p>
          <div className="flex flex-wrap gap-2">
            {availableThemes.map((t) => {
              const active = currentTheme === t.id;
              return (
                <Button
                  key={t.id}
                  variant={active ? "default" : "outline"}
                  size="sm"
                  onClick={() => setCustomTheme(t.id)}
                >
                  {t.primaryColor && (
                    <span
                      className="h-3 w-3 rounded-full mr-2 border"
                      style={{ backgroundColor: t.primaryColor }}
                    />
                  )}
                  {t.name}
                  {active && <Check className="h-4 w-4 ml-2" />}
                </Button>
              );
            })}
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Font</p>
          <div className="flex flex-wrap gap-2">
            {FONTS.map((f) => {
              const active = fontType === f.value;
              return (
                <Button
                  key={f.value}
                  variant={active ? "default" : "outline"}
                  size="sm"
                  onClick={() => setFontType(f.value)}
                >
                  {f.label}
                  {active && <Check className="h-4 w-4 ml-2" />}
                </Button>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
