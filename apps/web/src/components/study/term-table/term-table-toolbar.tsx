import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  AdaptiveMenu,
  AdaptiveMenuContent,
  AdaptiveMenuItem,
  AdaptiveMenuSeparator,
} from "@/components/ui/adaptive-menu";
import {
  CheckCircle,
  Brain,
  Copy,
  Download,
  Trash2,
  MoreHorizontal,
  Plus,
} from "lucide-react";
import type { Table } from "@tanstack/react-table";
import { TermAddDialog } from "./term-add-dialog";

import type { Term } from "@/types";

interface TermTableToolbarProps {
  table: Table<Term>;
  globalFilter: string;
  onGlobalFilterChange: (value: string) => void;
  cardsCount: number;
  deckId: string;
}

export function TermTableToolbar({
  table,
  globalFilter,
  onGlobalFilterChange,
  cardsCount,
  deckId,
}: TermTableToolbarProps) {
  const selectedRowsCount = table.getFilteredSelectedRowModel().rows.length;
  const hasSelectedRows = selectedRowsCount > 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-col lg:flex-row gap-4 items-stretch lg:items-center justify-between">
        {/* Search */}
        <div className="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center min-w-0 flex-1">
          <Input
            placeholder="Search terms..."
            value={globalFilter}
            onChange={(e) => onGlobalFilterChange(e.target.value)}
            className="w-full sm:max-w-sm"
          />
        </div>

        {/* Actions and Stats */}
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 lg:flex-shrink-0">
          {/* Selected Items Actions */}
          {hasSelectedRows && (
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <span className="text-sm text-muted-foreground text-center sm:text-left whitespace-nowrap">
                {selectedRowsCount} of {cardsCount} selected
              </span>
              <AdaptiveMenu
                title="Bulk Actions"
                trigger={
                  <Button
                    variant="outline"
                    size="default"
                    className="w-full sm:w-auto"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                    <span className="ml-2">Actions</span>
                  </Button>
                }
              >
                <AdaptiveMenuContent align="end">
                  <AdaptiveMenuItem>
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Mark as Mastered
                  </AdaptiveMenuItem>
                  <AdaptiveMenuItem>
                    <Brain className="h-4 w-4 mr-2" />
                    Mark as Learning
                  </AdaptiveMenuItem>
                  <AdaptiveMenuSeparator />
                  <AdaptiveMenuItem>
                    <Copy className="h-4 w-4 mr-2" />
                    Duplicate Terms
                  </AdaptiveMenuItem>
                  <AdaptiveMenuItem>
                    <Download className="h-4 w-4 mr-2" />
                    Export Selected
                  </AdaptiveMenuItem>
                  <AdaptiveMenuSeparator />
                  <AdaptiveMenuItem variant="destructive">
                    <Trash2 className="h-4 w-4 mr-2" />
                    Delete Selected
                  </AdaptiveMenuItem>
                </AdaptiveMenuContent>
              </AdaptiveMenu>
            </div>
          )}

          {/* Term Count and Add Button */}
          {!hasSelectedRows && (
            <div className="text-sm text-muted-foreground text-center sm:text-left whitespace-nowrap">
              {cardsCount} {cardsCount === 1 ? "term" : "terms"}
            </div>
          )}

          <TermAddDialog
            deckId={deckId}
            trigger={
              <Button size="default" className="w-full sm:w-auto">
                <Plus className="h-4 w-4" />
                <span className="ml-2">Add Term</span>
              </Button>
            }
          />
        </div>
      </div>
    </div>
  );
}
