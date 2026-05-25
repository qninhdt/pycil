"use client";

import React, { useState, useEffect, useCallback, useMemo, memo } from "react";

import type { Term } from "@/types/term";
import { cn } from "@/lib";

// --- Constants ---
const TEXTURE_STYLE = {
  backgroundImage:
    "radial-gradient(hsl(var(--muted-foreground) / 0.1) 1px, transparent 1px)",
  backgroundSize: "3px 3px",
} as const;

// Flashcard component for rendering a single flashcard with flip animation
interface FlashcardProps {
  readonly term: Term;
  readonly className?: string;
}

export const Flashcard = memo<FlashcardProps>(({ term, className }) => {
  // isRevealed=false: glass front on top blurring the back; true: front fades out to reveal back
  const [isRevealed, setIsRevealed] = useState(false);
  // When faded out, disable pointer events so back is interactive
  const [frontInteractive, setFrontInteractive] = useState(true);

  useEffect(() => {
    // Reset card state when term changes
    setIsRevealed(false);
    setFrontInteractive(true);
  }, [term.id]);

  useEffect(() => {
    // small delay to toggle pointer events after fade completes
    const t = setTimeout(() => setFrontInteractive(!isRevealed), 320);
    return () => clearTimeout(t);
  }, [isRevealed]);

  const handleFlip = useCallback(() => {
    setIsRevealed((prev) => !prev);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleFlip();
      }
    },
    [handleFlip]
  );

  // Memoized class names for front card
  const frontCardClasses = useMemo(
    () =>
      [
        "absolute inset-0 z-30 rounded-xl",
        // Primary-tinted glass, stronger tint when no backdrop support
        "bg-primary/20 supports-[backdrop-filter]:bg-primary/10",
        // Backdrop tuning for both modes
        "backdrop-blur-2xl backdrop-saturate-150 dark:backdrop-saturate-200 backdrop-brightness-110 dark:backdrop-brightness-125 backdrop-contrast-110 dark:backdrop-contrast-125",
        // Subtle outline matching tint
        "border border-primary/30 dark:border-primary/20 shadow-lg ring-1 ring-inset ring-primary/20 dark:ring-primary/15",
        // animation: simple fade out
        "transition-opacity duration-300 ease-out",
        isRevealed ? "opacity-0" : "opacity-100",
        frontInteractive ? "pointer-events-auto" : "pointer-events-none",
        "flex items-center justify-center p-8 sm:p-10 md:p-12 cursor-pointer overflow-hidden",
      ].join(" "),
    [isRevealed, frontInteractive]
  );

  return (
    <div className={cn("relative select-none", className)}>
      {/* Outer glow around the whole card (primary color) */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-1 rounded-xl bg-primary/20 blur-xl opacity-35 dark:opacity-40"
      />
      {/* Back card (solid, dark/light aware) */}
      <div
        className="absolute inset-0 z-10 rounded-xl border bg-card text-card-foreground shadow-sm flex items-center justify-center p-8 sm:p-10 md:p-12"
        onClick={handleFlip}
        role="button"
        aria-label={`Reveal definition: ${term.definition}`}
        tabIndex={-1}
      >
        <div className="w-full h-full flex flex-col items-center justify-center text-center gap-3">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">
            Definition
          </div>
          <div className="text-xl sm:text-2xl md:text-3xl font-medium leading-relaxed break-words">
            {term.definition}
          </div>
        </div>
      </div>

      {/* Front glass card (semi-transparent, backdrop blur) */}
      <div
        className={frontCardClasses}
        onClick={handleFlip}
        role="button"
        aria-pressed={isRevealed}
        aria-label={`Flashcard term: ${term.term}. Press to reveal definition`}
        tabIndex={0}
        onKeyDown={handleKeyDown}
      >
        {/* Subtle texture */}
        <div
          className="pointer-events-none absolute inset-0 rounded-[inherit] opacity-[0.12]"
          aria-hidden="true"
          style={TEXTURE_STYLE}
        />
        <div className="relative w-full h-full flex flex-col items-center justify-center text-center gap-2">
          <div className="text-xs uppercase tracking-wide text-primary/70">
            Term
          </div>
          <div className="text-2xl sm:text-3xl md:text-4xl font-semibold break-words text-foreground">
            {term.term}
          </div>
          <div className="mt-4 text-xs text-primary/60">Tap to reveal</div>
        </div>
      </div>
    </div>
  );
});

Flashcard.displayName = "Flashcard";
