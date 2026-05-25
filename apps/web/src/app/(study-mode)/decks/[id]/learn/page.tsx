"use client";

import React from "react";
import { use } from "react";
import { LearningSessionComponent } from "@/components/study/learn";
import { useDeckTerms } from "@/lib/api-hooks/use-terms";

interface LearnPageProps {
  params: Promise<{ id: string }>;
}

export default function LearnPage({ params }: LearnPageProps) {
  const { id } = use(params);
  const { data: rows = [], isLoading } = useDeckTerms(id);

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

  return (
    <div className="container mx-auto pt-8">
      <div className="max-w-4xl mx-auto">
        <LearningSessionComponent deckId={id} />
      </div>
    </div>
  );
}
