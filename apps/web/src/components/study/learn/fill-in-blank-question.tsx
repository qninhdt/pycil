"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CheckCircle2, XCircle } from "lucide-react";

type FillData = {
  prompt: string;
  explanation?: string;
};

interface FillInBlankQuestionProps {
  data: FillData;
  onSubmit: (answer: string) => Promise<{
    is_correct: boolean;
    reason?: string;
  } | null>;
  onNext: () => void;
}

export function FillInBlankQuestion({
  data,
  onSubmit,
  onNext,
}: FillInBlankQuestionProps) {
  const [text, setText] = useState("");
  const [result, setResult] = useState<{
    is_correct: boolean;
    reason?: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      const r = await onSubmit(text.trim());
      setResult(r);
    } finally {
      setBusy(false);
    }
  };

  if (result) {
    return (
      <div className="space-y-4">
        <div
          className={
            result.is_correct
              ? "flex items-center gap-2 text-green-600"
              : "flex items-center gap-2 text-destructive"
          }
        >
          {result.is_correct ? (
            <CheckCircle2 className="h-5 w-5" />
          ) : (
            <XCircle className="h-5 w-5" />
          )}
          <span className="font-medium">
            {result.is_correct ? "Correct" : "Not quite"}
          </span>
        </div>
        {data.explanation ? (
          <p className="text-sm text-muted-foreground">{data.explanation}</p>
        ) : null}
        <Button onClick={onNext}>Next</Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-base font-medium">{data.prompt}</p>
      <Input
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Missing word…"
        autoFocus
        disabled={busy}
        maxLength={80}
      />
      <Button type="submit" disabled={!text.trim() || busy}>
        Submit
      </Button>
    </form>
  );
}
