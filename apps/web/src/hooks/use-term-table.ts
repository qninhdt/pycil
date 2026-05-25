import { useState, useMemo, useEffect } from "react";
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  useReactTable,
  type PaginationState,
  type SortingState,
  type ColumnDef,
} from "@tanstack/react-table";
import type { Term } from "@/types";

interface UseTermTableProps {
  data: Term[];
  createColumns: (state: {
    expandedRows: Record<string, boolean>;
    setExpandedRows: React.Dispatch<
      React.SetStateAction<Record<string, boolean>>
    >;
  }) => ColumnDef<Term>[];
}

export function useTermTable({ data, createColumns }: UseTermTableProps) {
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize: 10,
  });

  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");
  const [expandedRows, setExpandedRows] = useState<Record<string, boolean>>({});

  const columns = useMemo(
    () => createColumns({ expandedRows, setExpandedRows }),
    [expandedRows, setExpandedRows, createColumns]
  );

  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    onSortingChange: setSorting,
    enableSortingRemoval: true,
    enableMultiSort: false,
    getPaginationRowModel: getPaginationRowModel(),
    onPaginationChange: setPagination,
    getFilteredRowModel: getFilteredRowModel(),
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: "includesString",
    autoResetPageIndex: false, // Prevent automatic page reset
    state: {
      sorting,
      pagination,
      globalFilter,
    },
  });

  // Reset page index when data changes, but do it in useEffect to avoid render-time state updates
  useEffect(() => {
    if (
      table.getPageCount() > 0 &&
      pagination.pageIndex >= table.getPageCount()
    ) {
      setPagination((prev) => ({ ...prev, pageIndex: 0 }));
    }
  }, [data, table, pagination.pageIndex]);

  return {
    table,
    columns,
    expandedRows,
    setExpandedRows,
    globalFilter,
    setGlobalFilter,
  };
}
