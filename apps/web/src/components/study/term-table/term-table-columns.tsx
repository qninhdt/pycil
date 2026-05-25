import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";
import type { ColumnDef } from "@tanstack/react-table";
import type { Term } from "@/types";

interface CreateTermTableColumnsProps {
  expandedRows: Record<string, boolean>;
  setExpandedRows: React.Dispatch<
    React.SetStateAction<Record<string, boolean>>
  >;
}

export function createTermTableColumns({
  expandedRows,
  setExpandedRows,
}: CreateTermTableColumnsProps): ColumnDef<Term>[] {
  return [
    {
      id: "select",
      header: ({ table }) => (
        <Checkbox
          checked={
            table.getIsAllPageRowsSelected() ||
            (table.getIsSomePageRowsSelected() && "indeterminate")
          }
          onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(value) => row.toggleSelected(!!value)}
          aria-label="Select row"
        />
      ),
      size: 25,
      enableSorting: false,
    },
    {
      header: "Term",
      accessorKey: "term",
      cell: ({ row }) => (
        <div className="font-medium w-full flex items-center">
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 flex-shrink-0"
            onClick={() => {
              const isExpanded = expandedRows[row.id];
              setExpandedRows((prev) => ({
                ...prev,
                [row.id]: !isExpanded,
              }));
            }}
          >
            <ChevronRight
              className={cn(
                "h-4 w-4 transition-transform duration-200",
                expandedRows[row.id] && "transform rotate-90"
              )}
            />
          </Button>
          <div
            className="truncate flex-1 flex items-center gap-2"
            title={row.getValue("term")}
          >
            <span>{row.getValue("term")}</span>
            {row.original.isRecentlyAdded && (
              <Badge variant="secondary" className="text-xs">
                New
              </Badge>
            )}
          </div>
        </div>
      ),
      size: 100,
    },
    {
      header: "Description",
      accessorKey: "definition",
      cell: ({ row }) => {
        const definition = row.getValue("definition") as string;
        return (
          <div className="w-full">
            <div
              className="text-sm text-muted-foreground break-words truncate"
              title={definition}
            >
              {definition}
            </div>
          </div>
        );
      },
    },
    {
      header: "Status",
      accessorKey: "mastered",
      cell: ({ row }) => {
        const mastered = row.getValue("mastered") as boolean;
        const difficulty = row.original.difficulty;

        let statusText: string;
        let statusStyles: string;

        if (mastered) {
          statusText = "Mastered";
          statusStyles = "bg-accent text-accent-foreground";
        } else if (difficulty === "easy") {
          statusText = "Learning";
          statusStyles = "bg-primary text-primary-foreground";
        } else {
          statusText = "New";
          statusStyles = "bg-secondary text-secondary-foreground";
        }

        return (
          <div className="flex justify-start">
            <Badge
              className={cn(
                "rounded-full border-none focus-visible:outline-none whitespace-nowrap text-xs",
                statusStyles
              )}
            >
              {statusText}
            </Badge>
          </div>
        );
      },
      size: 75,
    },
  ];
}
