import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ChevronFirstIcon,
  ChevronLastIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from "lucide-react";
import type { Table } from "@tanstack/react-table";
import type { Term } from "@/types";

interface TermTablePaginationProps {
  table: Table<Term>;
  tableId: string;
}

export function TermTablePagination({
  table,
  tableId,
}: TermTablePaginationProps) {
  const pagination = table.getState().pagination;

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
      {/* Page Size Selector */}
      <div className="flex items-center gap-3">
        <Label htmlFor={tableId} className="max-sm:sr-only">
          Rows per page
        </Label>
        <Select
          value={pagination.pageSize.toString()}
          onValueChange={(value) => table.setPageSize(Number(value))}
        >
          <SelectTrigger id={tableId} className="w-fit whitespace-nowrap">
            <SelectValue placeholder="Select number of results" />
          </SelectTrigger>
          <SelectContent className="[&_*[role=option]]:ps-2 [&_*[role=option]]:pe-8 [&_*[role=option]>span]:start-auto [&_*[role=option]>span]:end-2">
            {[5, 10, 25, 50].map((pageSize) => (
              <SelectItem key={pageSize} value={pageSize.toString()}>
                {pageSize}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Current Page Info */}
      <div className="text-muted-foreground flex grow justify-center sm:justify-end text-sm whitespace-nowrap">
        <p
          className="text-muted-foreground text-sm whitespace-nowrap"
          aria-live="polite"
        >
          <span className="text-foreground">
            {pagination.pageIndex * pagination.pageSize + 1}-
            {Math.min(
              Math.max(
                pagination.pageIndex * pagination.pageSize +
                  pagination.pageSize,
                0
              ),
              table.getRowCount()
            )}
          </span>{" "}
          of{" "}
          <span className="text-foreground">
            {table.getRowCount().toString()}
          </span>
        </p>
      </div>

      {/* Navigation Buttons */}
      <div className="flex items-center gap-2">
        <Button
          size="icon"
          variant="outline"
          className="disabled:pointer-events-none disabled:opacity-50"
          onClick={() => table.firstPage()}
          disabled={!table.getCanPreviousPage()}
          aria-label="Go to first page"
        >
          <ChevronFirstIcon size={16} aria-hidden="true" />
        </Button>

        <Button
          size="icon"
          variant="outline"
          className="disabled:pointer-events-none disabled:opacity-50"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
          aria-label="Go to previous page"
        >
          <ChevronLeftIcon size={16} aria-hidden="true" />
        </Button>

        <Button
          size="icon"
          variant="outline"
          className="disabled:pointer-events-none disabled:opacity-50"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
          aria-label="Go to next page"
        >
          <ChevronRightIcon size={16} aria-hidden="true" />
        </Button>

        <Button
          size="icon"
          variant="outline"
          className="disabled:pointer-events-none disabled:opacity-50"
          onClick={() => table.lastPage()}
          disabled={!table.getCanNextPage()}
          aria-label="Go to last page"
        >
          <ChevronLastIcon size={16} aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}
