"use client";

import React, { useRef, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { Sparkles } from "lucide-react";

interface UseInSentenceCardProps {
  prompt?: string;
  value: string;
  onChange: (val: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  isGrading: boolean;
}

export function UseInSentenceCard({
  prompt,
  value,
  onChange,
  onSubmit,
  disabled,
  isGrading,
}: UseInSentenceCardProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!disabled && !isGrading) {
      textareaRef.current?.focus();
    }
  }, [disabled, isGrading]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && e.ctrlKey && value.trim() && !disabled && !isGrading) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <Card className="border-2 shadow-sm">
      <CardHeader className="pb-4">
        <div className="flex items-center gap-2 mb-2">
          <Badge variant="outline" className="text-xs font-mono">
            Viết câu (AI Evaluation)
          </Badge>
          <Badge className="bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30 gap-1 text-xs">
            <Sparkles className="w-3 h-3" /> AI Graded
          </Badge>
        </div>
        <CardTitle className="text-xl md:text-2xl font-bold tracking-tight text-foreground">
          {prompt || "Write a complete sentence using the word in context:"}
        </CardTitle>
      </CardHeader>

      <CardContent className="space-y-6">
        <div className="space-y-2">
          <label className="text-sm font-medium text-muted-foreground flex justify-between">
            <span>Câu trả lời của bạn:</span>
            <span className="text-xs">{value.length} ký tự</span>
          </label>
          <Textarea
            ref={textareaRef}
            value={value}
            disabled={disabled || isGrading}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Viết một câu tiếng Anh hoàn chỉnh chứa từ/cụm từ trên..."
            rows={4}
            className="text-base p-4 rounded-xl border-2 resize-none focus-visible:ring-primary"
          />
        </div>

        {isGrading && (
          <div className="flex items-center justify-center gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-300">
            <Spinner className="w-5 h-5" />
            <span className="text-sm font-medium animate-pulse">
              AI đang chấm điểm và phân tích ngữ pháp câu của bạn...
            </span>
          </div>
        )}

        <div className="pt-2 flex justify-end">
          <Button
            onClick={onSubmit}
            disabled={disabled || isGrading || !value.trim()}
            size="lg"
            className="w-full md:w-auto font-semibold px-8 gap-2"
          >
            {isGrading ? (
              <>
                <Spinner className="w-4 h-4" /> Đang chấm bài...
              </>
            ) : (
              "Nộp bài (Ctrl + Enter)"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
