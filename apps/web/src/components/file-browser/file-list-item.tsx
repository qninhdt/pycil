"use client";

import React, { memo, useCallback, useMemo, useState } from "react";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import {
  AdaptiveMenu,
  AdaptiveMenuContent,
  AdaptiveMenuItem,
  AdaptiveMenuSeparator,
} from "../ui/adaptive-menu";
import type { TermDeck } from "@/types";
import {
  MoreHorizontal,
  Edit,
  Share,
  Trash2,
  Star,
  Pin,
  ExternalLink,
} from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { FileIcon } from "./file-icon";
import { DeleteConfirmDialog } from "@/components/dialogs/delete-confirm-dialog";
import {
  useToggleStar,
  useTogglePin,
} from "@/lib/api-hooks/use-nodes";
import { apiErrorMessage } from "@/lib/api-error-copy";

interface FileListItemProps {
  readonly item: TermDeck;
  readonly viewMode?: "grid" | "list";
  readonly onEdit?: (item: TermDeck) => void;
  readonly onShare?: (item: TermDeck) => void;
}

function getItemHref(item: TermDeck): string {
  if (item.isShortcut) return "#";
  if (item.isFolder) return `/folders/${item.id}`;
  return `/decks/${item.id}`;
}

/**
 * Memoized grid card component
 */
const GridCard = memo<FileListItemProps>(
  ({ item, onEdit, onShare }) => {
    const href = useMemo(() => getItemHref(item), [item]);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const toggleStar = useToggleStar();
    const togglePin = useTogglePin();

    const handleStar = useCallback(
      (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        toggleStar.mutate(item.id, {
          onError: (err) => toast.error(apiErrorMessage(err, "Could not star")),
        });
      },
      [toggleStar, item.id]
    );

    const handlePin = useCallback(() => {
      togglePin.mutate(item.id, {
        onError: (err) => toast.error(apiErrorMessage(err, "Could not pin")),
      });
    }, [togglePin, item.id]);

    const handleDelete = useCallback(() => setDeleteOpen(true), []);

    const handleMenuClick = useCallback((e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
    }, []);

    const handleMenuPointerDown = useCallback((e: React.PointerEvent) => {
      e.stopPropagation();
    }, []);

    return (
      <Card className="group hover:shadow-md transition-shadow h-full relative flex flex-col py-2">
        <Link
          href={href}
          className="absolute inset-0 z-0"
          aria-label={`Open ${item.title}`}
        />
        <CardHeader className="relative z-10 flex-shrink-0">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <FileIcon
                item={item}
                className="h-5 w-5 text-primary"
                showShortcutBadge
                showPinBadge
              />
              <div className="flex-1 min-w-0">
                <CardTitle className="text-sm truncate leading-tight">
                  {item.title}
                </CardTitle>
              </div>
            </div>

            <div className="flex items-center gap-1 flex-shrink-0">
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 hover:text-yellow-500 transition-colors relative z-20"
                onClick={handleStar}
                aria-label={`Star ${item.title}`}
              >
                <Star className="h-4 w-4" />
              </Button>

              <AdaptiveMenu
                title="Actions"
                trigger={
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 transition-opacity flex-shrink-0 relative z-20"
                    onClick={handleMenuClick}
                    onPointerDown={handleMenuPointerDown}
                    aria-label={`Actions for ${item.title}`}
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                }
              >
                <AdaptiveMenuContent>
                  {item.isShortcut && (
                    <AdaptiveMenuItem>
                      <ExternalLink className="h-4 w-4" />
                      Open target
                    </AdaptiveMenuItem>
                  )}
                  <AdaptiveMenuItem onClick={() => onEdit?.(item)}>
                    <Edit className="h-4 w-4" />
                    {item.isShortcut ? "Edit shortcut" : "Edit"}
                  </AdaptiveMenuItem>
                  <AdaptiveMenuItem onClick={handleStar}>
                    <Star className="h-4 w-4" />
                    Favorite
                  </AdaptiveMenuItem>
                  <AdaptiveMenuItem onClick={handlePin}>
                    <Pin className="h-4 w-4" />
                    {item.isPinned ? "Unpin" : "Pin"}
                  </AdaptiveMenuItem>
                  <AdaptiveMenuItem onClick={() => onShare?.(item)}>
                    <Share className="h-4 w-4" />
                    Share
                  </AdaptiveMenuItem>
                  <AdaptiveMenuSeparator />
                  <AdaptiveMenuItem
                    className="text-destructive"
                    onClick={handleDelete}
                  >
                    <Trash2 className="h-4 w-4" />
                    {item.isShortcut ? "Delete shortcut" : "Delete"}
                  </AdaptiveMenuItem>
                </AdaptiveMenuContent>
              </AdaptiveMenu>
            </div>
          </div>
        </CardHeader>

        <CardContent className="flex-1 flex flex-col">
          <div className="flex items-center justify-between text-xs text-muted-foreground mb-3 flex-shrink-0">
            <div className="flex items-center gap-2 flex-wrap">
              {item.isShortcut && (
                <>
                  <span className="bg-primary/10 text-primary px-2 py-1 rounded flex-shrink-0">
                    Shortcut
                  </span>
                  <span className="flex-shrink-0">→ {item.targetType}</span>
                </>
              )}
              {item.isFolder && (
                <span className="flex-shrink-0">
                  {item.deckCount} {item.deckCount === 1 ? "deck" : "decks"}
                </span>
              )}
            </div>
            {item.cardCount > 0 && !item.isFolder && (
              <span className="flex-shrink-0">{item.cardCount} cards</span>
            )}
          </div>

          {/* Progress bar for all items */}
          <div className="space-y-1 flex-shrink-0">
            <div className="w-full bg-muted rounded-full h-1.5">
              <div
                className="bg-primary h-1.5 rounded-full transition-all"
                style={{ width: `${item.masteryProgress}%` }}
                aria-label={`Progress: ${item.masteryProgress}%`}
              />
            </div>
          </div>
        </CardContent>
        <DeleteConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          nodeId={item.id}
          nodeName={item.title}
          isFolder={!!item.isFolder}
          childCount={item.deckCount}
        />
      </Card>
    );
  }
);

GridCard.displayName = "GridCard";

/**
 * Memoized list item component
 */
const ListItem = memo<FileListItemProps>(
  ({ item, onEdit, onShare }) => {
    const href = useMemo(() => getItemHref(item), [item]);
    const [deleteOpen, setDeleteOpen] = useState(false);
    const toggleStar = useToggleStar();
    const togglePin = useTogglePin();

    const handleStar = useCallback(
      (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        toggleStar.mutate(item.id, {
          onError: (err) => toast.error(apiErrorMessage(err, "Could not star")),
        });
      },
      [toggleStar, item.id]
    );

    const handlePin = useCallback(() => {
      togglePin.mutate(item.id, {
        onError: (err) => toast.error(apiErrorMessage(err, "Could not pin")),
      });
    }, [togglePin, item.id]);

    const handleDelete = useCallback(() => setDeleteOpen(true), []);

    return (
      <div className="flex items-center justify-between p-3 rounded-lg hover:bg-muted/50 transition-colors group min-h-[4rem]">
        <Link
          href={href}
          className="flex items-center gap-3 flex-1 min-w-0"
          aria-label={`Open ${item.title}`}
        >
          <FileIcon
            item={item}
            className="h-5 w-5 text-primary"
            showShortcutBadge
            showPinBadge
          />
          <div className="flex-1 min-w-0">
            <h3 className="font-medium text-sm break-words hyphens-auto line-clamp-1 sm:line-clamp-2">
              {item.title}
            </h3>
            <div className="flex items-center gap-1 sm:gap-2 text-xs text-muted-foreground flex-wrap">
              {item.isShortcut && (
                <>
                  <span className="bg-primary/10 text-primary px-2 py-0.5 rounded text-xs flex-shrink-0">
                    Shortcut
                  </span>
                  <span className="hidden sm:inline flex-shrink-0">
                    → {item.targetType}
                  </span>
                </>
              )}
              {item.isFolder && (
                <span className="whitespace-nowrap flex-shrink-0">
                  {item.deckCount} {item.deckCount === 1 ? "deck" : "decks"}
                </span>
              )}
              {item.cardCount > 0 && !item.isFolder && (
                <span className="whitespace-nowrap flex-shrink-0">
                  {item.cardCount} cards
                </span>
              )}
              <span className="hidden sm:inline">•</span>
              <span className="hidden md:inline truncate">
                {item.author || "Unknown"}
              </span>
              <span className="hidden sm:inline">•</span>
              <span className="hidden sm:inline whitespace-nowrap flex-shrink-0">
                Updated {item.updatedAt}
              </span>
            </div>
          </div>
        </Link>

        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Progress bar for all items */}
          <div className="hidden lg:flex items-center gap-3">
            <div className="w-16 xl:w-20 bg-muted rounded-full h-1.5">
              <div
                className="bg-primary h-1.5 rounded-full transition-all"
                style={{ width: `${item.masteryProgress}%` }}
                aria-label={`Progress: ${item.masteryProgress}%`}
              />
            </div>
          </div>

          {/* Star button */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 hover:text-yellow-500 transition-colors flex-shrink-0"
            onClick={handleStar}
            aria-label={`Star ${item.title}`}
          >
            <Star className="h-4 w-4" />
          </Button>

          {/* Three dots menu */}
          <AdaptiveMenu
            title="Actions"
            trigger={
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 transition-opacity flex-shrink-0"
                aria-label={`Actions for ${item.title}`}
              >
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            }
          >
            <AdaptiveMenuContent>
              {item.isShortcut && (
                <AdaptiveMenuItem>
                  <ExternalLink className="h-4 w-4" />
                  Open target
                </AdaptiveMenuItem>
              )}
              <AdaptiveMenuItem onClick={() => onEdit?.(item)}>
                <Edit className="h-4 w-4" />
                {item.isShortcut ? "Edit shortcut" : "Edit"}
              </AdaptiveMenuItem>
              <AdaptiveMenuItem onClick={handleStar}>
                <Star className="h-4 w-4" />
                Favorite
              </AdaptiveMenuItem>
              <AdaptiveMenuItem onClick={handlePin}>
                <Pin className="h-4 w-4" />
                {item.isPinned ? "Unpin" : "Pin"}
              </AdaptiveMenuItem>
              <AdaptiveMenuItem onClick={() => onShare?.(item)}>
                <Share className="h-4 w-4" />
                Share
              </AdaptiveMenuItem>
              <AdaptiveMenuSeparator />
              <AdaptiveMenuItem
                className="text-destructive"
                onClick={handleDelete}
              >
                <Trash2 className="h-4 w-4" />
                {item.isShortcut ? "Delete shortcut" : "Delete"}
              </AdaptiveMenuItem>
            </AdaptiveMenuContent>
          </AdaptiveMenu>
        </div>
        <DeleteConfirmDialog
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          nodeId={item.id}
          nodeName={item.title}
          isFolder={!!item.isFolder}
          childCount={item.deckCount}
        />
      </div>
    );
  }
);

ListItem.displayName = "ListItem";

/**
 * Optimized file list item component
 */
export const FileListItem = memo<FileListItemProps>(
  ({ item, viewMode = "list", onEdit, onShare }) => {
    if (viewMode === "grid") {
      return (
        <GridCard
          item={item}
          viewMode={viewMode}
          onEdit={onEdit}
          onShare={onShare}
        />
      );
    }

    return (
      <ListItem
        item={item}
        viewMode={viewMode}
        onEdit={onEdit}
        onShare={onShare}
      />
    );
  }
);

FileListItem.displayName = "FileListItem";
