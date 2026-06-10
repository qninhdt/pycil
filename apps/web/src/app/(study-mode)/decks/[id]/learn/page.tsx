"use client";

import React from "react";
import { use, useState } from "react";
import { LearningSessionComponent } from "@/components/study/learn";
import { ThemePicker } from "@/components/study/learn/theme-picker";
import { Button } from "@/components/ui/button";
import { useDeckTerms } from "@/lib/api-hooks/use-terms";

interface LearnPageProps {
  params: Promise<{ id: string }>;
}

export default function LearnPage({ params }: LearnPageProps) {
  const { id } = use(params);
  const { data: rows = [], isLoading } = useDeckTerms(id);
  const [themeId, setThemeId] = useState<string | null>(null);
  const [started, setStarted] = useState(false);

  if (isLoading) {
    return (
      <div className="container mx-auto pt-8">
        <p className="text-sm text-muted-foreground">Loading terms…</p>
      </div>
    );
  }

  const ready = rows.filter((r) => r.definition && r.job_status !== "pending");

  if (ready.length === 0) {
    return (
      <div className="container mx-auto pt-8">
        <div className="max-w-md mx-auto text-center space-y-2">
          <h2 className="text-2xl font-semibold">No terms ready</h2>
          <p className="text-muted-foreground">
            Add terms or wait for definitions to finish generating before
            starting a learning session.
          </p>
        </div>
      </div>
    );
  }

  if (!started) {
    return (
      <div className="container mx-auto pt-8">
        <div className="max-w-md mx-auto space-y-6">
          <h2 className="text-2xl font-semibold text-center">Start learning</h2>
          <ThemePicker value={themeId} onChange={setThemeId} />
          <Button className="w-full" onClick={() => setStarted(true)}>
            Start session
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto pt-8">
      <div className="max-w-4xl mx-auto">
        <LearningSessionComponent deckId={id} themeId={themeId} />
      </div>
    </div>
  );
}
