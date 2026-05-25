"use client";

import { use } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { Settings, X, Layers, BookOpen } from "lucide-react";
import { useNode } from "@/lib/api-hooks/use-nodes";

interface Props {
  children: React.ReactNode;
  params: Promise<{
    id: string;
  }>;
}

const MODES = {
  flashcard: { label: "Flashcard", icon: Layers },
  learn: { label: "Learn", icon: BookOpen },
};

export default function StudyDeckLayout({ children, params }: Props) {
  const { id } = use(params);
  const router = useRouter();
  const pathname = usePathname();
  const { data: deck, isLoading } = useNode(id);

  const currentMode = pathname.includes("/learn") ? "learn" : "flashcard";
  const Icon = MODES[currentMode].icon;

  const handleModeChange = (mode: string) => {
    router.push(`/decks/${id}/${mode}`);
  };

  const handleClose = () => {
    router.push(`/decks/${id}`);
  };

  if (!isLoading && !deck) {
    return <div>Deck not found</div>;
  }

  return (
    <div className="h-screen bg-background">
      <header className="fixed top-0 z-40 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="flex h-16 items-center px-4 gap-4">
          <div className="flex items-center gap-4">
            <Select value={currentMode} onValueChange={handleModeChange}>
              <SelectTrigger>
                <Icon className="h-4 w-4 mr-2" />
                <div className="mr-2 hidden md:inline-block">
                  {MODES[currentMode].label}
                </div>
              </SelectTrigger>
              <SelectContent>
                {Object.entries(MODES).map(([key, { label, icon: Icon }]) => (
                  <SelectItem key={key} value={key}>
                    <div className="flex items-center gap-2">
                      <Icon className="h-4 w-4" />
                      <span>{label}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <Button
              variant="ghost"
              size="icon"
              className="h-9 w-9"
              aria-label="Settings"
              disabled
            >
              <Settings className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={handleClose}
              className="h-9 w-9"
              aria-label="Close study mode"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </header>

      <main className="h-full px-6 lg:px-8 pt-24 pb-8">
        <div className="h-full max-w-5xl mx-auto">{children}</div>
      </main>
    </div>
  );
}
