"use client";

import { FileToolbar } from "@/components/file-browser/file-toolbar";
import { FileList } from "@/components/file-browser/file-list";
import { Folder } from "lucide-react";
import { useState, use } from "react";
import { useAppSettings } from "@/providers";
import { useNode, useNodeChildren } from "@/lib/api-hooks/use-nodes";
import { nodesToTermDecks } from "@/lib/adapters";

interface FolderPageProps {
  params: Promise<{ id: string }>;
}

export default function FolderPage({ params }: FolderPageProps) {
  const { id } = use(params);
  const [sortBy, setSortBy] = useState("Last Updated");
  const { viewMode, setViewMode, isLoaded } = useAppSettings();
  const { data: node } = useNode(id);
  const { data: children = [], isLoading, isError } = useNodeChildren(id);

  if (!isLoaded) return null;

  const items = nodesToTermDecks(children);

  return (
    <div className="space-y-6">
      <FileToolbar
        sortBy={sortBy}
        setSortBy={setSortBy}
        viewMode={viewMode}
        setViewMode={setViewMode}
      />
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading folder…</p>
      ) : isError ? (
        <p className="text-sm text-destructive">Could not load folder.</p>
      ) : (
        <FileList
          items={items}
          viewMode={viewMode}
          title={node?.name ?? ""}
          emptyState={{
            icon: <Folder className="h-12 w-12 text-muted-foreground mx-auto" />,
            title: "No term sets yet",
            description:
              "This folder is empty. Add some term sets to get started.",
            buttonText: "Add term set",
          }}
        />
      )}
    </div>
  );
}
