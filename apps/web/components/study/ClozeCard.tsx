"use client";

import React, { useRef, useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

interface ClozeCardProps {
  stemWithBlank?: string;
  value: string;
  onChange: (val: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}

export function ClozeCard({
  stemWithBlank,
  value,
  onChange,
  onSubmit,
  disabled,
}: ClozeCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!disabled) {
      inputRef.current?.focus();
    }
  }, [disabled]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && value.trim() && !disabled) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <Card className="border-2 shadow-sm">
      <CardHeader className="pb-4">
        <Badge variant="outline" className="w-fit text-xs font-mono mb-2">
          Cloze Test (Điền từ)
        </Badge>
        <CardTitle className="text-xl md:text-2xl font-semibold leading-relaxed text-foreground bg-muted/20 p-5 rounded-xl border">
          {stemWithBlank || "Fill in the missing word:"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        <div className="space-y-2">
          <label className="text-sm font-medium text-muted-foreground">
            Nhập từ còn thiếu:
          </label>
          <Input
            ref={inputRef}
            type="text"
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Gõ từ tại đây..."
            className="text-lg py-6 px-4 rounded-xl border-2 focus-visible:ring-primary"
            autoComplete="off"
            autoCorrect="off"
            spellCheck="false"
          />
        </div>

        <div className="pt-2 flex justify-end">
          <Button
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            size="lg"
            className="w-full md:w-auto font-semibold px-8"
          >
            Kiểm tra (Enter)
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
