"use client";

import React, { useEffect } from "react";
import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function AuthError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Auth boundary error caught:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center p-6 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive mb-4">
        <AlertCircle className="size-6" />
      </div>
      <h2 className="text-xl font-semibold">Authentication Error</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {error.message || "An error occurred during authentication."}
      </p>
      <Button onClick={reset} variant="outline" className="mt-6">
        Try again
      </Button>
    </div>
  );
}
