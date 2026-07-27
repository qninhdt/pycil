"use client";

import React, { useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

interface ContextualMcqCardProps {
  stem?: string;
  options?: string[];
  selectedIndex: string | null;
  onSelectOption: (index: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}

const OPTION_LABELS = ["A", "B", "C", "D"];

export function ContextualMcqCard({
  stem,
  options = [],
  selectedIndex,
  onSelectOption,
  onSubmit,
  disabled,
}: ContextualMcqCardProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (disabled) return;
      const keyMap: Record<string, string> = { "1": "0", "2": "1", "3": "2", "4": "3" };
      if (keyMap[e.key] !== undefined && Number(keyMap[e.key]) < options.length) {
        onSelectOption(keyMap[e.key]);
      } else if (e.key === "Enter" && selectedIndex !== null) {
        e.preventDefault();
        onSubmit();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [disabled, options.length, selectedIndex, onSelectOption, onSubmit]);

  return (
    <Card className="border-2 shadow-sm">
      <CardHeader className="pb-4">
        <Badge variant="outline" className="w-fit text-xs font-mono mb-2">
          Contextual MCQ
        </Badge>
        <CardTitle className="text-lg md:text-xl font-medium leading-relaxed text-foreground bg-muted/30 p-4 rounded-xl border">
          {stem || "Choose the best option to complete the context:"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 gap-3">
          {options.map((option, idx) => {
            const indexStr = String(idx);
            const isSelected = selectedIndex === indexStr;
            return (
              <button
                key={idx}
                type="button"
                disabled={disabled}
                onClick={() => onSelectOption(indexStr)}
                className={`flex items-start gap-3 p-4 rounded-xl border-2 text-left transition-all font-medium ${
                  isSelected
                    ? "border-primary bg-primary/10 text-primary shadow-sm"
                    : "border-border hover:border-primary/50 hover:bg-accent/50 text-foreground"
                } ${disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
              >
                <span
                  className={`flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold shrink-0 border ${
                    isSelected
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-muted text-muted-foreground border-border"
                  }`}
                >
                  {OPTION_LABELS[idx] || idx + 1}
                </span>
                <span className="text-base leading-relaxed pt-0.5">{option}</span>
              </button>
            );
          })}
        </div>

        <div className="pt-2 flex justify-end">
          <Button
            onClick={onSubmit}
            disabled={disabled || selectedIndex === null}
            size="lg"
            className="w-full md:w-auto font-semibold px-8"
          >
            Kiểm tra (Enter)
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
