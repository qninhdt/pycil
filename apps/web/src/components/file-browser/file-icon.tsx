"use client";

import { cn } from "@/lib/utils";
import { Archive, FileText, Folder, Link as LinkIcon, Pin } from "lucide-react";
import React from "react";
import type { TermDeck } from "@/types";

type FileKind = "deck" | "folder" | "collection";

export interface FileIconProps {
  item?: TermDeck;
  kind?: FileKind;
  className?: string;
  showShortcutBadge?: boolean;
  showPinBadge?: boolean;
  badgeColor?: "muted" | "foreground";
}

function resolveKindFromItem(item: TermDeck | undefined): FileKind | undefined {
  if (!item) return undefined;
  if (item.isShortcut) {
    if (item.targetType === "folder") return "folder";
    return "deck";
  }
  if (item.isFolder) return "folder";
  return "deck";
}

export function FileIcon({
  item,
  kind,
  className,
  showShortcutBadge,
  showPinBadge,
  badgeColor = "muted",
}: FileIconProps) {
  const resolvedKind = kind ?? resolveKindFromItem(item) ?? "deck";
  const Icon =
    resolvedKind === "folder"
      ? Folder
      : resolvedKind === "collection"
      ? Archive
      : FileText;

  return (
    <div className="relative inline-flex items-center justify-center">
      <Icon className={cn("h-5 w-5", className)} />
      {item?.isShortcut && showShortcutBadge && (
        <LinkIcon
          className={cn(
            "h-3 w-3 absolute -bottom-1 -right-1 bg-background rounded-full z-10 pointer-events-none",
            badgeColor === "foreground"
              ? "text-current"
              : "text-muted-foreground"
          )}
        />
      )}
      {item?.isPinned && showPinBadge && (
        <Pin
          className={cn(
            "h-3 w-3 absolute -top-1 -right-1 bg-background rounded-full z-10 pointer-events-none",
            badgeColor === "foreground" ? "text-current" : "text-orange-500"
          )}
        />
      )}
    </div>
  );
}
