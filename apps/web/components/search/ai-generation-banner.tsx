"use client";

import React, { useEffect, useState } from "react";
import { Sparkles, CheckCircle2, AlertCircle, Loader2, X } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useTaskSnapshot } from "@/lib/realtime/use-task-snapshot";

interface AiGenerationBannerProps {
  taskId: string | null;
  query: string;
  onCompleted: () => void;
  onDismiss: () => void;
}

export function AiGenerationBanner({
  taskId,
  query,
  onCompleted,
  onDismiss,
}: AiGenerationBannerProps) {
  const [progress, setProgress] = useState(15);
  const [hasNotified, setHasNotified] = useState(false);
  const snapshot = useTaskSnapshot(taskId);
  const currentStatus = snapshot?.status ?? "queued";

  // Progress animation based on current status
  useEffect(() => {
    if (currentStatus === "queued") {
      setProgress(25);
    } else if (currentStatus === "running") {
      const interval = setInterval(() => {
        setProgress((prev) => (prev < 85 ? prev + 5 : prev));
      }, 500);
      return () => clearInterval(interval);
    } else if (currentStatus === "succeeded") {
      setProgress(100);
      if (!hasNotified) {
        setHasNotified(true);
        onCompleted();
      }
    } else if (currentStatus === "failed" || currentStatus === "expired") {
      setProgress(100);
    }
  }, [currentStatus, hasNotified, onCompleted]);

  if (!taskId) return null;

  return (
    <Card className="border-primary/40 bg-gradient-to-r from-primary/10 via-primary/5 to-background shadow-md overflow-hidden animate-in fade-in slide-in-from-top-2">
      <CardContent className="p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {currentStatus === "succeeded" ? (
              <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
            ) : currentStatus === "failed" || currentStatus === "expired" ? (
              <AlertCircle className="h-5 w-5 text-destructive shrink-0" />
            ) : (
              <Loader2 className="h-5 w-5 text-primary animate-spin shrink-0" />
            )}

            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-foreground">
                  AI Generation for "{query}"
                </span>
                <Badge
                  variant={
                    currentStatus === "succeeded"
                      ? "default"
                      : currentStatus === "failed" || currentStatus === "expired"
                      ? "destructive"
                      : "secondary"
                  }
                  className="capitalize text-[10px]"
                >
                  {currentStatus}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                {currentStatus === "queued" && "Waiting in queue for AI processing..."}
                {currentStatus === "running" && "Generating definitions, phonetics, and example sentences..."}
                {currentStatus === "succeeded" && "Word definitions successfully generated!"}
                {(currentStatus === "failed" || currentStatus === "expired") && "Failed to generate word definitions. Please try again."}
              </p>
            </div>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={onDismiss}
            className="h-7 w-7 shrink-0 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Dismiss</span>
          </Button>
        </div>

        {(currentStatus === "queued" || currentStatus === "running") && (
          <Progress value={progress} className="h-1.5 bg-primary/20" />
        )}
      </CardContent>
    </Card>
  );
}
