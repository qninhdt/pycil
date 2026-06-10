import React, { memo } from "react";
import { Button } from "@/components/ui/button";
import { BookOpen, Layers } from "lucide-react";
import Link from "next/link";

interface StudyModesProps {
  readonly deckId: string;
}

// --- Constants ---
// v1 ships only Flashcard + Learn. Chat and Test were cut from v1 scope
// (no `/decks/[id]/chat` or `/decks/[id]/test` route exists), so linking to
// them produced 404s. Re-add the options here when those routes ship.
const STUDY_MODE_OPTIONS = [
  {
    href: "flashcard",
    icon: Layers,
    label: "Flashcard",
    description: "Review with interactive flashcards",
  },
  {
    href: "learn",
    icon: BookOpen,
    label: "Learn",
    description: "Adaptive learning session",
  },
] as const;

/**
 * Memoized study mode button component
 */
const StudyModeButton = memo<{
  readonly deckId: string;
  readonly href: string;
  readonly icon: React.ComponentType<{ className?: string }>;
  readonly label: string;
  readonly description: string;
}>(({ deckId, href, icon: Icon, label, description }) => (
  <Button
    variant="outline"
    className="group h-auto items-start justify-start gap-3 p-4 text-left hover:border-primary/40 hover:bg-accent/50"
    asChild
  >
    <Link
      href={`/decks/${deckId}/${href}`}
      aria-label={`${label}: ${description}`}
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary transition-colors group-hover:bg-primary/15">
        <Icon className="h-5 w-5" aria-hidden="true" />
      </span>
      <span className="flex flex-col gap-0.5">
        <span className="font-semibold">{label}</span>
        <span className="text-xs font-normal text-muted-foreground">
          {description}
        </span>
      </span>
    </Link>
  </Button>
));

StudyModeButton.displayName = "StudyModeButton";

/**
 * Optimized study modes component
 */
export const StudyModes = memo<StudyModesProps>(({ deckId }) => (
  <div className="grid grid-cols-2 gap-4">
    {STUDY_MODE_OPTIONS.map((mode) => (
      <StudyModeButton
        key={mode.href}
        deckId={deckId}
        href={mode.href}
        icon={mode.icon}
        label={mode.label}
        description={mode.description}
      />
    ))}
  </div>
));

StudyModes.displayName = "StudyModes";
