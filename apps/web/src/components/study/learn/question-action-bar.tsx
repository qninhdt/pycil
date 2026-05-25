"use client";

import React from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { Volume2, HelpCircle, SkipForward } from "lucide-react";

interface QuestionActionBarProps {
  isNewWord?: boolean;
  onReadAloud: () => void;
  onGetHint: () => void;
  onSkip: () => void;
  className?: string;
}

export function QuestionActionBar({
  isNewWord = false,
  onReadAloud,
  onGetHint,
  onSkip,
  className,
}: QuestionActionBarProps) {
  return (
    <div className={cn("flex items-center justify-between gap-4", className)}>
      {/* Left side - Word badge */}
      <div className="flex items-center gap-2">
        {isNewWord && (
          <Badge variant="secondary" className="text-xs font-medium">
            New
          </Badge>
        )}
      </div>

      {/* Right side - Action buttons */}
      <div className="flex items-center gap-1">
        {/* Text to Speech */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onReadAloud}
          className="h-8 w-8"
          aria-label="Read question aloud"
        >
          <Volume2 className="h-4 w-4" />
        </Button>

        {/* Get Hint */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onGetHint}
          className="h-8 w-8"
          aria-label="Get hint"
        >
          <HelpCircle className="h-4 w-4" />
        </Button>

        {/* Skip / I don't know */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onSkip}
          className="h-8 w-8"
          aria-label="Skip question"
        >
          <SkipForward className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
