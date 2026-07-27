"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Spinner } from "@/components/ui/spinner";
import { BookOpen, Play, CheckCircle2, Award } from "lucide-react";
import type { NodeItem, FolderStats } from "@/lib/api/types";
import { startStudySessionAction } from "@/lib/actions/study";

interface DeckStudyCardProps {
  deck: NodeItem;
  stats?: FolderStats | null;
}

export function DeckStudyCard({ deck, stats }: DeckStudyCardProps) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const total = stats?.total ?? 0;
  const mastered = stats?.mastered ?? 0;
  const learned = stats?.learned ?? 0;
  const masteredPercent = total > 0 ? Math.round((mastered / total) * 100) : 0;

  const handleStartStudy = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const res = await startStudySessionAction(deck.id);
      if (res.firstState === "exhausted") {
        setMessage("Deck đã hoàn thành! Không có từ nào cần ôn lúc này.");
      } else {
        router.push(`/study/${res.sessionId}`);
      }
    } catch (err) {
      console.error("Failed to start study session:", err);
      setMessage("Không thể khởi tạo phiên học. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="flex flex-col justify-between border-2 hover:border-primary/50 transition-all shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-2 mb-1">
          <Badge variant="outline" className="text-xs font-mono">
            {deck.type}
          </Badge>
          <Badge
            variant={deck.visibility === "PUBLIC" ? "default" : "secondary"}
            className="text-[10px] uppercase font-bold"
          >
            {deck.visibility}
          </Badge>
        </div>
        <CardTitle className="text-xl font-bold tracking-tight text-foreground line-clamp-1">
          {deck.name}
        </CardTitle>
        {deck.description && (
          <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
            {deck.description}
          </p>
        )}
      </CardHeader>

      <CardContent className="space-y-4">
        {stats ? (
          <div className="space-y-3 bg-muted/30 p-3.5 rounded-xl border">
            <div className="flex justify-between items-center text-xs font-medium">
              <span className="text-muted-foreground flex items-center gap-1.5">
                <BookOpen className="w-3.5 h-3.5 text-primary" /> Tổng số từ:
              </span>
              <span className="font-bold text-foreground">{total} từ</span>
            </div>

            <div className="flex justify-between items-center text-xs font-medium">
              <span className="text-muted-foreground flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" /> Đã học:
              </span>
              <span className="font-bold text-foreground">{learned} từ</span>
            </div>

            <div className="flex justify-between items-center text-xs font-medium">
              <span className="text-muted-foreground flex items-center gap-1.5">
                <Award className="w-3.5 h-3.5 text-amber-500" /> Thành thạo (Mastered):
              </span>
              <span className="font-bold text-emerald-600 dark:text-emerald-400">
                {mastered} từ ({masteredPercent}%)
              </span>
            </div>

            <Progress value={masteredPercent} className="h-2 rounded-full" />
          </div>
        ) : (
          <div className="text-xs text-muted-foreground py-2 text-center">
            Đang tải thống kê...
          </div>
        )}

        {message && (
          <p className="text-xs font-medium text-amber-600 dark:text-amber-400 bg-amber-500/10 p-2.5 rounded-lg border border-amber-500/20 text-center">
            {message}
          </p>
        )}
      </CardContent>

      <CardFooter className="pt-2">
        <Button
          onClick={handleStartStudy}
          disabled={loading || total === 0}
          className="w-full font-semibold gap-2 py-5"
          size="lg"
        >
          {loading ? (
            <>
              <Spinner className="w-4 h-4" /> Đang khởi tạo...
            </>
          ) : (
            <>
              <Play className="w-4 h-4 fill-current" /> Bắt đầu học
            </>
          )}
        </Button>
      </CardFooter>
    </Card>
  );
}
