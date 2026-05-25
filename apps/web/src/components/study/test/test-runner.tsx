"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type TestItem = {
  item_id: string;
  position: number;
  type: string;
  stem?: string;
  prompt?: string;
  options?: string[];
};

interface TestRunnerProps {
  runId: string;
  deckId: string;
  items: TestItem[];
  onComplete: (summary: {
    correct_count: number;
    total: number;
    score_pct: number;
  }) => void;
}

export function TestRunner({ runId, deckId, items, onComplete }: TestRunnerProps) {
  const [idx, setIdx] = useState(0);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [choice, setChoice] = useState<number | null>(null);

  const item = items[idx];
  if (!item) return null;

  const submit = async () => {
    if (busy) return;
    let userAnswer: string;
    if (item.type === "MULTIPLE_CHOICE") {
      if (choice === null) return;
      userAnswer = String(choice);
    } else {
      if (!text.trim()) return;
      userAnswer = text.trim();
    }

    setBusy(true);
    try {
      await fetch(
        `/api/core/decks/${deckId}/test/runs/${runId}/answers`,
        {
          method: "POST",
          credentials: "include",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ item_id: item.item_id, user_answer: userAnswer }),
        }
      );

      const next = idx + 1;
      if (next >= items.length) {
        const res = await fetch(
          `/api/core/decks/${deckId}/test/runs/${runId}/complete`,
          { method: "POST", credentials: "include" }
        );
        if (res.ok) {
          onComplete(await res.json());
        }
      } else {
        setIdx(next);
        setText("");
        setChoice(null);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        Question {idx + 1} of {items.length}
      </p>
      <p className="text-base font-medium">{item.stem ?? item.prompt}</p>

      {item.type === "MULTIPLE_CHOICE" && item.options ? (
        <div className="space-y-2">
          {item.options.map((opt, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setChoice(i)}
              className={
                choice === i
                  ? "block w-full text-left rounded-md border-2 border-primary bg-primary/10 px-3 py-2 text-sm"
                  : "block w-full text-left rounded-md border px-3 py-2 text-sm hover:bg-muted"
              }
              disabled={busy}
            >
              {opt}
            </button>
          ))}
        </div>
      ) : (
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Your answer…"
          autoFocus
          disabled={busy}
        />
      )}

      <Button onClick={submit} disabled={busy}>
        {idx + 1 === items.length ? "Finish" : "Next"}
      </Button>
    </div>
  );
}
