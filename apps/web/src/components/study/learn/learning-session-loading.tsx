"use client";

import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface LearningSessionLoadingProps {
  className?: string;
}

export function LearningSessionLoading({
  className,
}: LearningSessionLoadingProps) {
  return (
    <Card className={cn("w-full mx-auto", className)}>
      <CardHeader>
        <CardTitle className="text-center">
          <div className="animate-pulse bg-muted h-6 w-48 mx-auto rounded" />
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Progress bar skeleton */}
        <div className="space-y-2">
          <div className="animate-pulse bg-muted h-4 w-full rounded" />
          <div className="animate-pulse bg-muted h-2 w-3/4 rounded" />
        </div>

        {/* Question skeleton */}
        <div className="space-y-4">
          <div className="animate-pulse bg-muted h-8 w-2/3 rounded" />
          <div className="space-y-2">
            <div className="animate-pulse bg-muted h-12 w-full rounded" />
            <div className="animate-pulse bg-muted h-12 w-full rounded" />
            <div className="animate-pulse bg-muted h-12 w-full rounded" />
            <div className="animate-pulse bg-muted h-12 w-full rounded" />
          </div>
        </div>

        {/* Action buttons skeleton */}
        <div className="flex gap-2 justify-center">
          <div className="animate-pulse bg-muted h-8 w-20 rounded" />
          <div className="animate-pulse bg-muted h-8 w-20 rounded" />
          <div className="animate-pulse bg-muted h-8 w-20 rounded" />
        </div>
      </CardContent>
    </Card>
  );
}
