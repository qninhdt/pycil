"use client";

import { FileToolbar } from "@/components/file-browser/file-toolbar";
import { FileList } from "@/components/file-browser/file-list";
import { useState } from "react";
import { useAppSettings } from "@/providers";
import { useRootNodes } from "@/lib/api-hooks/use-nodes";
import { nodesToTermDecks } from "@/lib/adapters";
import type { TermDeck } from "@/types";

function sortPinnedFirst(items: TermDeck[]): TermDeck[] {
  return [...items].sort((a, b) => {
    if (!!a.isPinned !== !!b.isPinned) return a.isPinned ? -1 : 1;
    return (b.updatedAt ?? "").localeCompare(a.updatedAt ?? "");
  });
}

export default function CollectionPage() {
  const [sortBy, setSortBy] = useState("Last Updated");
  const { viewMode, setViewMode, isLoaded } = useAppSettings();
  const { data: nodes = [], isLoading, isError } = useRootNodes();

  if (!isLoaded) return null;

  const items = nodesToTermDecks(nodes);
  const folders = sortPinnedFirst(items.filter((it) => it.isFolder));
  const files = sortPinnedFirst(items.filter((it) => !it.isFolder));

  return (
    <div className="space-y-6">
      <FileToolbar
        sortBy={sortBy}
        setSortBy={setSortBy}
        viewMode={viewMode}
        setViewMode={setViewMode}
      />
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading your collection…</p>
      ) : isError ? (
        <p className="text-sm text-destructive">
          Could not load your collection. Try again.
        </p>
      ) : (
        <FileList
          sections={[
            { title: "Folders", items: folders },
            { title: "Files", items: files },
          ]}
          viewMode={viewMode}
        />
      )}
    </div>
  );
}
