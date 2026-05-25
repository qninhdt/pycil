"use client";

import React, { memo, useMemo } from "react";
import type { TermDeck } from "@/types";
import { FileListItem } from "./file-list-item";
import { Button } from "../ui/button";

interface FileListSection {
  readonly title?: string;
  readonly items: TermDeck[];
}

interface FileListProps {
  readonly sections?: FileListSection[];
  readonly items?: TermDeck[];
  readonly viewMode: "grid" | "list";
  readonly title?: string;
  readonly emptyState?: {
    readonly icon?: React.ReactNode;
    readonly title: string;
    readonly description: string;
    readonly buttonText?: string;
    readonly buttonAction?: () => void;
  };
}

// --- Constants ---
const DEFAULT_EMPTY_STATE = {
  title: "No materials yet",
  description: "Create your first term deck to start studying",
  buttonText: "Create your first deck",
} as const;

const GRID_CLASSES =
  "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 auto-rows-fr";
const LIST_CLASSES = "space-y-2";

/**
 * Utility function to sort items with pinned items first
 */
function sortItemsWithPinnedFirst(items: TermDeck[]): TermDeck[] {
  return [...items].sort((a, b) => {
    // Pinned items come first
    if (a.isPinned && !b.isPinned) return -1;
    if (!a.isPinned && b.isPinned) return 1;
    // If both are pinned or both are not pinned, maintain original order
    return 0;
  });
}

/**
 * Memoized empty state component
 */
const EmptyState = memo<{
  readonly state: {
    readonly icon?: React.ReactNode;
    readonly title: string;
    readonly description: string;
    readonly buttonText?: string;
    readonly buttonAction?: () => void;
  };
}>(({ state }) => (
  <div className="text-center py-12">
    <div className="mx-auto max-w-sm">
      {state.icon && (
        <div className="mb-4" aria-hidden="true">
          {state.icon}
        </div>
      )}
      <h3 className="text-lg font-medium">{state.title}</h3>
      <p className="text-muted-foreground mt-2">{state.description}</p>
      {state.buttonText && (
        <Button
          className="mt-4"
          onClick={state.buttonAction}
          aria-label={state.buttonText}
        >
          {state.buttonText}
        </Button>
      )}
    </div>
  </div>
));

EmptyState.displayName = "EmptyState";

/**
 * Memoized file section component
 */
const FileSection = memo<{
  readonly section: FileListSection;
  readonly viewMode: "grid" | "list";
  readonly index: number;
}>(({ section, viewMode, index }) => {
  const sortedItems = useMemo(
    () => sortItemsWithPinnedFirst(section.items),
    [section.items]
  );

  if (section.items.length === 0) return null;

  const containerClasses = viewMode === "grid" ? GRID_CLASSES : LIST_CLASSES;

  return (
    <div key={index} className="space-y-3">
      {section.title && (
        <h2 className="text-sm font-medium text-muted-foreground">
          {section.title}
        </h2>
      )}
      <div className={containerClasses}>
        {sortedItems.map((item) => (
          <FileListItem key={item.id} item={item} viewMode={viewMode} />
        ))}
      </div>
    </div>
  );
});

FileSection.displayName = "FileSection";

/**
 * Optimized file list component
 */
export const FileList = memo<FileListProps>(
  ({ sections, items, viewMode, title = "Your Files", emptyState }) => {
    // Calculate state and memoize heavy operations
    const { totalItems, sortedItems, displayState } = useMemo(() => {
      let totalCount = 0;
      let sorted: TermDeck[] = [];
      const state = emptyState || DEFAULT_EMPTY_STATE;

      if (sections) {
        totalCount = sections.reduce(
          (acc, section) => acc + section.items.length,
          0
        );
      } else {
        const itemsToRender = items || [];
        totalCount = itemsToRender.length;
        sorted = sortItemsWithPinnedFirst(itemsToRender);
      }

      return {
        totalItems: totalCount,
        sortedItems: sorted,
        displayState: state,
      };
    }, [sections, items, emptyState]);

    // Handle sections mode
    if (sections) {
      if (totalItems === 0) {
        return <EmptyState state={displayState} />;
      }

      return (
        <div className="space-y-6">
          {sections.map((section, index) => (
            <FileSection
              key={index}
              section={section}
              viewMode={viewMode}
              index={index}
            />
          ))}
        </div>
      );
    }

    // Handle items mode
    if (totalItems === 0) {
      return <EmptyState state={displayState} />;
    }

    const containerClasses = viewMode === "grid" ? GRID_CLASSES : LIST_CLASSES;

    return (
      <div className="space-y-3">
        {title && (
          <h2 className="text-sm font-medium text-muted-foreground">{title}</h2>
        )}
        <div className={containerClasses}>
          {sortedItems.map((item) => (
            <FileListItem key={item.id} item={item} viewMode={viewMode} />
          ))}
        </div>
      </div>
    );
  }
);

FileList.displayName = "FileList";
