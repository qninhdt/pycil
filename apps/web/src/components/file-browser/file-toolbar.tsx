"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronDown, MoreHorizontal, Grid3X3, List, Plus } from "lucide-react";
import { CreateNodeDialog } from "@/components/dialogs/create-node-dialog";
import { CreateShortcutDialog } from "@/components/dialogs/create-shortcut-dialog";
import type { NodeType, UUID } from "@/types/domain";

interface FileToolbarProps {
  sortBy: string;
  setSortBy: (sortBy: string) => void;
  viewMode: "grid" | "list";
  setViewMode: (viewMode: "grid" | "list") => void;
  parentNodeId?: UUID | null;
}

export function FileToolbar({
  sortBy,
  setSortBy,
  viewMode,
  setViewMode,
  parentNodeId = null,
}: FileToolbarProps) {
  const [createOpen, setCreateOpen] = useState(false);
  const [createType, setCreateType] = useState<NodeType>("FOLDER");
  const [shortcutOpen, setShortcutOpen] = useState(false);

  const openCreate = (type: NodeType) => {
    setCreateType(type);
    setCreateOpen(true);
  };

  return (
    <div className="flex items-center justify-between gap-2">
      <div className="flex items-center gap-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm">
              <Plus className="h-4 w-4 mr-1" />
              New
              <ChevronDown className="h-4 w-4 ml-1" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            <DropdownMenuItem onClick={() => openCreate("FOLDER")}>
              New folder
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => openCreate("DECK")}>
              New deck
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setShortcutOpen(true)}>
              New shortcut
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <div className="flex items-center gap-2 flex-shrink-0">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="text-muted-foreground">
              <ChevronDown className="h-4 w-4 mr-2" />
              <span className="hidden sm:inline">{sortBy}</span>
              <span className="sm:hidden">Sort</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => setSortBy("Last Updated")}>
              Last Updated
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setSortBy("Name")}>
              Name
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => setSortBy("Created")}>
              Created
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        <div className="flex items-center border rounded-md">
          <Button
            variant={viewMode === "grid" ? "default" : "ghost"}
            size="sm"
            onClick={() => setViewMode("grid")}
            className="rounded-r-none"
          >
            <Grid3X3 className="h-4 w-4" />
          </Button>
          <Button
            variant={viewMode === "list" ? "default" : "ghost"}
            size="sm"
            onClick={() => setViewMode("list")}
            className="rounded-l-none"
          >
            <List className="h-4 w-4" />
          </Button>
        </div>

        <Button variant="ghost" size="icon" className="h-8 w-8 hidden sm:flex">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </div>

      <CreateNodeDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        parentNodeId={parentNodeId}
        defaultType={createType}
      />
      <CreateShortcutDialog
        open={shortcutOpen}
        onOpenChange={setShortcutOpen}
        parentNodeId={parentNodeId}
      />
    </div>
  );
}
