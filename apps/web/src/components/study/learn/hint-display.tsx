"use client";

import React from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";

interface HintDisplayProps {
  hint: string | null;
  className?: string;
}

export function HintDisplay({ hint, className }: HintDisplayProps) {
  if (!hint) return null;

  return (
    <Card className={cn(className)}>
      <CardContent>
        <div className="flex items-center gap-2">
          <Lightbulb className="h-4 w-4" />
          <span className="text-sm font-medium">Hint:</span>
          <span className="text-sm">{hint}</span>
        </div>
      </CardContent>
    </Card>
  );
}
