"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CheckCircle2, XCircle } from "lucide-react";

type WriteData = {
  prompt: string;
  explanation?: string;
};

interface WriteQuestionProps {
  data: WriteData;
  onSubmit: (answer: string) => Promise<{
    is_correct: boolean;
    reason?: string;
  } | null>;
  onNext: () => void;
}

export function WriteQuestion({ data, onSubmit, onNext }: WriteQuestionProps) {
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
          {result.reason ? (
            <span className="text-xs text-muted-foreground">
              ({result.reason})
            </span>
          ) : null}
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
      <textarea
        className="flex min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
        value={text}
        onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setText(e.target.value)}
        placeholder="Type your answer…"
        rows={4}
        autoFocus
        disabled={busy}
      />
      <Button type="submit" disabled={!text.trim() || busy}>
        Submit
      </Button>
    </form>
  );
}
