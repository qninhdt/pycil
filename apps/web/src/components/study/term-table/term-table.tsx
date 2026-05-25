import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import {
  flexRender,
  type ColumnDef,
  type Table as TableType,
} from "@tanstack/react-table";
import {
  ChevronUpIcon,
  ChevronDownIcon,
  BookOpen,
  Edit,
  Brain,
} from "lucide-react";
import * as React from "react";
import type { Term } from "@/types";

interface TermTableProps {
  table: TableType<Term>;
  columns: ColumnDef<Term>[];
  expandedRows: Record<string, boolean>;
  setExpandedRows: React.Dispatch<
    React.SetStateAction<Record<string, boolean>>
  >;
}

export function TermTable({
  table,
  columns,
  expandedRows,
  setExpandedRows,
}: TermTableProps) {
  return (
    <div className="rounded-md border overflow-hidden">
      <div className="overflow-x-auto scrollbar-thin">
        <Table className="table-fixed w-full">
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="hover:bg-transparent">
                {headerGroup.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    style={{ width: `${header.getSize()}px` }}
                    className="h-11"
                  >
                    {header.isPlaceholder ? null : header.column.getCanSort() ? (
                      <div
                        className={cn(
                          header.column.getCanSort() &&
                            "flex h-full cursor-pointer items-center gap-1 select-none"
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                        onKeyDown={(e) => {
                          if (
                            header.column.getCanSort() &&
                            (e.key === "Enter" || e.key === " ")
                          ) {
                            e.preventDefault();
                            header.column.getToggleSortingHandler()?.(e);
                          }
                        }}
                        tabIndex={header.column.getCanSort() ? 0 : undefined}
                      >
                        {flexRender(
                          header.column.columnDef.header,
                          header.getContext()
                        )}
                        {header.column.getCanSort() &&
                          header.column.getIsSorted() && (
                            <>
                              {header.column.getIsSorted() === "asc" && (
                                <ChevronUpIcon
                                  className="shrink-0 opacity-60"
                                  size={16}
                                  aria-hidden="true"
                                />
                              )}
                              {header.column.getIsSorted() === "desc" && (
                                <ChevronDownIcon
                                  className="shrink-0 opacity-60"
                                  size={16}
                                  aria-hidden="true"
                                />
                              )}
                            </>
                          )}
                      </div>
                    ) : (
                      flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <React.Fragment key={row.id}>
                  <TableRow
                    data-state={row.getIsSelected() && "selected"}
                    className={cn(
                      "cursor-pointer hover:bg-muted/50",
                      row.original.isRecentlyAdded &&
                        "bg-accent/50 border-accent hover:bg-accent/70"
                    )}
                    onClick={() => {
                      const isExpanded = expandedRows[row.id];
                      setExpandedRows((prev) => ({
                        ...prev,
                        [row.id]: !isExpanded,
                      }));
                    }}
                  >
                    {row.getVisibleCells().map((cell) => (
                      <TableCell
                        key={cell.id}
                        className="py-3"
                        onClick={(e) => {
                          // Prevent row click when clicking on checkbox or expand button
                          if (
                            cell.column.id === "select" ||
                            cell.column.id === "expand"
                          ) {
                            e.stopPropagation();
                          }
                        }}
                      >
                        {flexRender(
                          cell.column.columnDef.cell,
                          cell.getContext()
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                  {expandedRows[row.id] && (
                    <TableRow data-state={row.getIsSelected() && "selected"}>
                      <TableCell
                        colSpan={columns.length}
                        className={cn(
                          "py-6 border-t  max-w-full",
                          row.getIsSelected() ? "bg-muted/50" : "bg-muted/30"
                        )}
                      >
                        <div className="space-y-6 w-full">
                          {/* Main Content */}
                          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <div className="space-y-4">
                              <div>
                                <h4 className="font-medium text-sm text-muted-foreground mb-2">
                                  Term
                                </h4>
                                <p className="text-base">{row.original.term}</p>
                              </div>
                            </div>
                            <div className="space-y-4">
                              <div>
                                <h4 className="font-medium text-sm text-muted-foreground mb-2">
                                  Definition
                                </h4>
                                <p className="text-base text-wrap">
                                  {row.original.definition}
                                </p>
                              </div>
                            </div>
                          </div>

                          {/* Action Buttons */}
                          <div className="flex flex-wrap gap-2 pt-2 border-t">
                            <Button size="sm" variant="default">
                              <BookOpen className="h-4 w-4 mr-2" />
                              Study This Term
                            </Button>
                            <Button size="sm" variant="outline">
                              <Edit className="h-4 w-4 mr-2" />
                              Edit Term
                            </Button>
                            <Button size="sm" variant="outline">
                              <Brain className="h-4 w-4 mr-2" />
                              Practice Mode
                            </Button>
                          </div>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center"
                >
                  No terms found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
