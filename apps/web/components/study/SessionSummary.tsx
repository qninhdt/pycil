"use client";

import React from "react";
import Link from "next/link";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Trophy, CheckCircle2, RotateCcw, ArrowLeft, Target, Award } from "lucide-react";

interface SessionSummaryProps {
  completedCount: number;
  correctCount: number;
  masteredCount: number;
  onRestart?: () => void;
}

export function SessionSummary({
  completedCount,
  correctCount,
  masteredCount,
}: SessionSummaryProps) {
  const accuracyPercent =
    completedCount > 0 ? Math.round((correctCount / completedCount) * 100) : 100;

  return (
    <Card className="max-w-xl mx-auto border-2 shadow-lg text-center overflow-hidden animate-in zoom-in-95">
      <div className="bg-gradient-to-b from-primary/15 via-primary/5 to-transparent p-8 pb-4 flex flex-col items-center">
        <div className="w-20 h-20 rounded-full bg-primary/20 flex items-center justify-center text-primary mb-4 shadow-inner ring-8 ring-primary/10">
          <Trophy className="w-10 h-10 animate-bounce" />
        </div>
        <CardHeader className="p-0">
          <CardTitle className="text-2xl md:text-3xl font-extrabold tracking-tight text-foreground">
            Hoàn thành phiên học!
          </CardTitle>
          <p className="text-sm text-muted-foreground mt-1">
            Tuyệt vời! Bạn đã hoàn thành xuất sắc các thẻ ôn tập trong phiên này.
          </p>
        </CardHeader>
      </div>

      <CardContent className="p-8 pt-4 space-y-6">
        <div className="grid grid-cols-3 gap-4 bg-muted/30 p-4 rounded-2xl border">
          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium flex items-center justify-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-primary" /> Đã hoàn thành
            </div>
            <p className="text-xl md:text-2xl font-black text-foreground">{completedCount}</p>
          </div>

          <div className="space-y-1 border-x border-border/60">
            <div className="text-xs text-muted-foreground font-medium flex items-center justify-center gap-1">
              <Target className="w-3.5 h-3.5 text-emerald-500" /> Độ chính xác
            </div>
            <p className="text-xl md:text-2xl font-black text-emerald-600 dark:text-emerald-400">
              {accuracyPercent}%
            </p>
          </div>

          <div className="space-y-1">
            <div className="text-xs text-muted-foreground font-medium flex items-center justify-center gap-1">
              <Award className="w-3.5 h-3.5 text-amber-500" /> Thành thạo
            </div>
            <p className="text-xl md:text-2xl font-black text-amber-600 dark:text-amber-400">
              {masteredCount}
            </p>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Link
            href="/study"
            className={buttonVariants({
              variant: "default",
              size: "lg",
              className: "w-full sm:w-auto font-semibold gap-2",
            })}
          >
            <ArrowLeft className="w-4 h-4" /> Về danh sách Deck
          </Link>

          <Link
            href="/study"
            className={buttonVariants({
              variant: "outline",
              size: "lg",
              className: "w-full sm:w-auto font-semibold gap-2 border-2",
            })}
          >
            <RotateCcw className="w-4 h-4" /> Chọn Deck khác
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
