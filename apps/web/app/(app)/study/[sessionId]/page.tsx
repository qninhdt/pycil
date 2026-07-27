import React from "react";
import Link from "next/link";
import { SessionController } from "@/components/study/SessionController";
import { Button, buttonVariants } from "@/components/ui/button";
import { X, Brain } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export const metadata = {
  title: "Active Study Session | Pycil",
  description: "Interactive FSRS 4.5 Question Player",
};

export default async function ActiveSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;

  return (
    <div className="container max-w-4xl py-6 space-y-6">
      {/* Session Top Bar */}
      <div className="flex items-center justify-between border-b pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center text-primary">
            <Brain className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold tracking-tight text-foreground">
                Phiên ôn tập FSRS
              </h2>
              <Badge variant="outline" className="text-[10px] font-mono">
                Active
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground font-mono">
              ID: {sessionId.slice(0, 8)}...
            </p>
          </div>
        </div>

        <Link
          href="/study"
          className={buttonVariants({
            variant: "ghost",
            size: "sm",
            className: "gap-1.5 text-muted-foreground hover:text-foreground",
          })}
        >
          <X className="w-4 h-4" /> Thoát phiên học
        </Link>
      </div>

      {/* Main Controller */}
      <SessionController sessionId={sessionId} />
    </div>
  );
}
