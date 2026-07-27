"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { FolderPlus, Layers, Plus, Search, FolderOpen } from "lucide-react";
import type { NodeItem, NodeType } from "@/lib/api/types";
import { useNodeDetail, useNodes, useUpdateNodeVisibility } from "@/lib/query/nodes";
import { BreadcrumbNav } from "@/components/library/breadcrumb-nav";
import { NodeCard } from "@/components/library/node-card";
import { CreateFolderDialog } from "@/components/library/create-folder-dialog";
import { CreateDeckDialog } from "@/components/library/create-deck-dialog";
import { EditNodeDialog } from "@/components/library/edit-node-dialog";
import { MoveNodeDialog } from "@/components/library/move-node-dialog";
import { DeleteNodeDialog } from "@/components/library/delete-node-dialog";
import { FolderVocabularyTab } from "@/components/library/folder-vocabulary-tab";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty";

export default function LibraryPage() {
  const searchParams = useSearchParams();
  const folderId = searchParams.get("folderId");

  const [searchQuery, setSearchQuery] = useState("");
  const [createFolderOpen, setCreateFolderOpen] = useState(false);
  const [createDeckOpen, setCreateDeckOpen] = useState(false);

  const [editingNode, setEditingNode] = useState<NodeItem | null>(null);
  const [movingNode, setMovingNode] = useState<NodeItem | null>(null);
  const [deletingNode, setDeletingNode] = useState<NodeItem | null>(null);

  const [activeTab, setActiveTab] = useState<"nodes" | "vocabulary">("nodes");

  const { data: currentFolder } = useNodeDetail(folderId || "");
  const { data: nodesData, isLoading } = useNodes(folderId);
  const updateVisibility = useUpdateNodeVisibility();

  const handleToggleVisibility = (node: NodeItem) => {
    const nextVisibility = node.visibility === "PUBLIC" ? "PRIVATE" : "PUBLIC";
    updateVisibility.mutate({
      id: node.id,
      data: {
        visibility: nextVisibility,
        confirmSubtreePublication: nextVisibility === "PUBLIC",
      },
    });
  };

  const filteredNodes =
    nodesData?.items.filter((item) =>
      item.name.toLowerCase().includes(searchQuery.toLowerCase())
    ) || [];

  const breadcrumbItems = currentFolder ? [{ id: currentFolder.id, name: currentFolder.name }] : [];

  return (
    <div className="container max-w-6xl mx-auto p-6 space-y-6">
      <BreadcrumbNav items={breadcrumbItems} />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            {currentFolder ? currentFolder.name : "My Library"}
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            {currentFolder?.description || "Organize your vocabulary decks and folders."}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setCreateFolderOpen(true)}
            className="flex items-center gap-1.5"
          >
            <FolderPlus className="h-4 w-4 text-primary" />
            <span>New Folder</span>
          </Button>
          <Button
            size="sm"
            onClick={() => setCreateDeckOpen(true)}
            className="flex items-center gap-1.5"
          >
            <Plus className="h-4 w-4" />
            <span>New Deck</span>
          </Button>
        </div>
      </div>

      {folderId && (
        <div className="flex items-center gap-2 border-b border-border/60 pb-1">
          <button
            onClick={() => setActiveTab("nodes")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-all ${
              activeTab === "nodes"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Cấu trúc thư mục
          </button>
          <button
            onClick={() => setActiveTab("vocabulary")}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-all ${
              activeTab === "vocabulary"
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            Từ vựng trong thư mục
          </button>
        </div>
      )}

      <div className="flex items-center gap-3 bg-card p-2 rounded-xl border border-border/50">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search folders and decks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 bg-background/50 border-0 focus-visible:ring-1"
          />
        </div>
      </div>

      {activeTab === "vocabulary" && folderId ? (
        <FolderVocabularyTab folderId={folderId} />
      ) : isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full rounded-xl" />
          ))}
        </div>
      ) : filteredNodes.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
          {filteredNodes.map((node) => (
            <NodeCard
              key={node.id}
              node={node}
              onEdit={(n) => setEditingNode(n)}
              onMove={(n) => setMovingNode(n)}
              onToggleVisibility={handleToggleVisibility}
              onDelete={(n) => setDeletingNode(n)}
            />
          ))}
        </div>
      ) : (
        <div className="pt-6">
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <FolderOpen className="h-6 w-6 text-muted-foreground" />
              </EmptyMedia>
              <EmptyTitle>
                {searchQuery ? "No items match your search" : "This folder is empty"}
              </EmptyTitle>
              <EmptyDescription>
                {searchQuery
                  ? "Try searching for a different keyword or clear the search field."
                  : "Create a new folder or deck to start adding words."}
              </EmptyDescription>
            </EmptyHeader>
            {!searchQuery && (
              <EmptyContent>
                <div className="flex items-center gap-2 mt-2">
                  <Button variant="outline" size="sm" onClick={() => setCreateFolderOpen(true)}>
                    <FolderPlus className="h-4 w-4 mr-1.5" />
                    New Folder
                  </Button>
                  <Button size="sm" onClick={() => setCreateDeckOpen(true)}>
                    <Layers className="h-4 w-4 mr-1.5" />
                    New Deck
                  </Button>
                </div>
              </EmptyContent>
            )}
          </Empty>
        </div>
      )}

      {/* Separate Dialog Modals */}
      <CreateFolderDialog
        open={createFolderOpen}
        onOpenChange={setCreateFolderOpen}
        parentNodeId={folderId}
      />

      <CreateDeckDialog
        open={createDeckOpen}
        onOpenChange={setCreateDeckOpen}
        parentNodeId={folderId}
      />

      <EditNodeDialog
        node={editingNode}
        open={!!editingNode}
        onOpenChange={(open) => !open && setEditingNode(null)}
      />

      <MoveNodeDialog
        node={movingNode}
        open={!!movingNode}
        onOpenChange={(open) => !open && setMovingNode(null)}
      />

      <DeleteNodeDialog
        node={deletingNode}
        open={!!deletingNode}
        onOpenChange={(open) => !open && setDeletingNode(null)}
      />
    </div>
  );
}
