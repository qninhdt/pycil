import React from "react";
import { getSession } from "@/lib/auth/session";
import { createApiClient } from "@/lib/api/client";
import { StudyDeckGrid } from "@/components/study/StudyDeckGrid";
import type { NodeItem } from "@/lib/api/types";
import { BookOpenCheck, BrainCircuit } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export const metadata = {
  title: "Study Sessions | Pycil",
  description: "Spaced Repetition Learning powered by FSRS 4.5 algorithm",
};

export default async function StudyPage() {
  const session = await getSession();
  let rootDecks: NodeItem[] = [];

  if (session.isLoggedIn) {
    try {
      const client = createApiClient(session);
      const res = await client.getNodes(null, undefined, 100);
      rootDecks = res.items.filter((item) => item.type === "DECK" || item.type === "FOLDER");
    } catch (err) {
      console.error("Failed to load user decks for study page:", err);
    }
  }

  return (
    <div className="container max-w-6xl py-8 space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b pb-6">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-3xl font-extrabold tracking-tight text-foreground">
              Phiên học & Ôn tập
            </h1>
            <Badge className="bg-primary/10 text-primary border-primary/20 gap-1 text-xs py-1">
              <BrainCircuit className="w-3.5 h-3.5" /> FSRS 4.5 Powered
            </Badge>
          </div>
          <p className="text-base text-muted-foreground">
            Chọn bộ từ vựng (Deck) để bắt đầu phiên ôn tập được tối ưu hóa theo độ quên từ của bạn.
          </p>
        </div>

        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground bg-muted/40 px-4 py-2 rounded-xl border">
          <BookOpenCheck className="w-4 h-4 text-emerald-500" />
          <span>{rootDecks.length} bộ từ khả dụng</span>
        </div>
      </div>

      <StudyDeckGrid initialDecks={rootDecks} />
    </div>
  );
}
