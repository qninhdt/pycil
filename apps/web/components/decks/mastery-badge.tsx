"use client";

import { Badge } from "@/components/ui/badge";

interface MasteryBadgeProps {
  score?: number; // 0 - 100
}

export function getMasteryLevel(score: number = 0): {
  level: number;
  label: string;
  variant: "default" | "secondary" | "outline" | "destructive";
  className: string;
} {
  const rounded = Math.min(100, Math.max(0, Math.round(score)));

  if (rounded === 0) {
    return {
      level: 1,
      label: "Lvl 1 • New",
      variant: "secondary",
      className: "bg-slate-500/15 text-slate-700 dark:text-slate-300 border-slate-500/30",
    };
  }
  if (rounded <= 10) {
    return {
      level: 2,
      label: "Lvl 2",
      variant: "outline",
      className: "bg-rose-500/15 text-rose-700 dark:text-rose-400 border-rose-500/30",
    };
  }
  if (rounded <= 20) {
    return {
      level: 3,
      label: "Lvl 3",
      variant: "outline",
      className: "bg-orange-500/15 text-orange-700 dark:text-orange-400 border-orange-500/30",
    };
  }
  if (rounded <= 35) {
    return {
      level: 4,
      label: "Lvl 4",
      variant: "outline",
      className: "bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30",
    };
  }
  if (rounded <= 50) {
    return {
      level: 5,
      label: "Lvl 5",
      variant: "outline",
      className: "bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/30",
    };
  }
  if (rounded <= 65) {
    return {
      level: 6,
      label: "Lvl 6",
      variant: "outline",
      className: "bg-lime-500/15 text-lime-700 dark:text-lime-400 border-lime-500/30",
    };
  }
  if (rounded <= 79) {
    const level = rounded <= 72 ? 7 : 8;
    return {
      level,
      label: `Lvl ${level}`,
      variant: "outline",
      className: "bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30",
    };
  }
  if (rounded <= 90) {
    const level = rounded <= 85 ? 9 : 10;
    return {
      level,
      label: `Lvl ${level}`,
      variant: "outline",
      className: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30",
    };
  }

  return {
    level: 11,
    label: "Lvl 11 • Mastered",
    variant: "default",
    className: "bg-teal-500/20 text-teal-700 dark:text-teal-300 border-teal-500/40 font-semibold",
  };
}

export function MasteryBadge({ score = 0 }: MasteryBadgeProps) {
  const { label, className } = getMasteryLevel(score);

  return (
    <Badge
      variant="outline"
      className={`text-[11px] font-medium px-2 py-0.5 border ${className}`}
    >
      {label}
    </Badge>
  );
}
