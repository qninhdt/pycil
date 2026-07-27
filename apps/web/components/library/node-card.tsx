"use client";

import Link from "next/link";
import { Folder, Layers, Link2, MoreVertical, Edit, Move, Lock, Globe, Trash2 } from "lucide-react";
import type { NodeItem } from "@/lib/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface NodeCardProps {
  node: NodeItem;
  onEdit: (node: NodeItem) => void;
  onMove: (node: NodeItem) => void;
  onToggleVisibility: (node: NodeItem) => void;
  onDelete: (node: NodeItem) => void;
}

export function NodeCard({
  node,
  onEdit,
  onMove,
  onToggleVisibility,
  onDelete,
}: NodeCardProps) {
  const isFolder = node.type === "FOLDER";
  const isReference = node.type === "REFERENCE";
  const href = isFolder ? `/library?folderId=${node.id}` : `/decks/${node.id}`;

  return (
    <Card className="group relative hover:border-primary/50 transition-all shadow-sm hover:shadow-md">
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <Link href={href} className="flex items-start gap-3 flex-1 min-w-0">
            <div className="p-2.5 rounded-xl bg-primary/10 text-primary shrink-0 group-hover:scale-105 transition-transform">
              {isFolder ? (
                <Folder className="h-6 w-6 fill-primary/20" />
              ) : isReference ? (
                <Link2 className="h-6 w-6" />
              ) : (
                <Layers className="h-6 w-6" />
              )}
            </div>

            <div className="space-y-1 min-w-0 flex-1">
              <h3 className="font-semibold text-base leading-tight truncate group-hover:text-primary transition-colors">
                {node.name}
              </h3>
              {node.description && (
                <p className="text-xs text-muted-foreground line-clamp-2">
                  {node.description}
                </p>
              )}
            </div>
          </Link>

          <DropdownMenu>
            <DropdownMenuTrigger
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground shrink-0 focus-visible:outline-none"
            >
              <MoreVertical className="h-4 w-4" />
              <span className="sr-only">Actions</span>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem onClick={() => onEdit(node)}>
                <Edit className="h-4 w-4 mr-2" />
                Rename / Edit
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onMove(node)}>
                <Move className="h-4 w-4 mr-2" />
                Move location
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => onToggleVisibility(node)}>
                {node.visibility === "PUBLIC" ? (
                  <>
                    <Lock className="h-4 w-4 mr-2" />
                    Make Private
                  </>
                ) : (
                  <>
                    <Globe className="h-4 w-4 mr-2" />
                    Make Public
                  </>
                )}
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => onDelete(node)}
                className="text-destructive focus:text-destructive"
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground pt-3 border-t border-border/50">
          <Badge
            variant={node.visibility === "PUBLIC" ? "default" : "secondary"}
            className="text-[10px] uppercase tracking-wider font-semibold"
          >
            {node.visibility === "PUBLIC" ? (
              <span className="flex items-center gap-1">
                <Globe className="h-3 w-3" /> Public
              </span>
            ) : (
              <span className="flex items-center gap-1">
                <Lock className="h-3 w-3" /> Private
              </span>
            )}
          </Badge>

          <span className="text-[11px]">
            {isFolder ? "Folder" : isReference ? "Reference Deck" : "Deck"}
          </span>
        </div>
      </CardContent>
    </Card>
  );
}
