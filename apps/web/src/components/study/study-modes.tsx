import React, { memo } from "react";
import { Button } from "@/components/ui/button";
import { BookOpen, Layers, MessageSquare, ClipboardCheck } from "lucide-react";
import Link from "next/link";

interface StudyModesProps {
  readonly deckId: string;
}

// --- Constants ---
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
  {
    href: "chat",
    icon: MessageSquare,
    label: "Chat with AI",
    description: "Interactive AI study session",
  },
  {
    href: "test",
    icon: ClipboardCheck,
    label: "Test",
    description: "Take a practice test",
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
  <Button variant="outline" className="h-20 flex-col gap-2" asChild>
    <Link
      href={`/decks/${deckId}/${href}`}
      aria-label={`${label}: ${description}`}
    >
      <Icon className="h-6 w-6" aria-hidden="true" />
      <span>{label}</span>
    </Link>
  </Button>
));

StudyModeButton.displayName = "StudyModeButton";

/**
 * Optimized study modes component
 */
export const StudyModes = memo<StudyModesProps>(({ deckId }) => (
  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
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
