"use client";

import { use, useId, useMemo } from "react";

import {
  TermTableToolbar,
  TermTable,
  TermTablePagination,
  createTermTableColumns,
} from "@/components/study";
import { useTermTable } from "@/hooks/use-term-table";
import { useDeckTerms } from "@/lib/api-hooks/use-terms";
import { deckTermReadsToDeckTerms } from "@/lib/adapters";

interface Props {
  params: Promise<{ id: string }>;
}

export default function TermDeckTablePage({ params }: Props) {
  const { id } = use(params);
  const tableId = useId();

  const { data: rows = [], isLoading, isError } = useDeckTerms(id);

  const cards = useMemo(() => deckTermReadsToDeckTerms(rows), [rows]);

  const {
    table,
    columns,
    expandedRows,
    setExpandedRows,
    globalFilter,
    setGlobalFilter,
  } = useTermTable({ data: cards, createColumns: createTermTableColumns });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading terms…</p>;
  }
  if (isError) {
    return <p className="text-sm text-destructive">Could not load terms.</p>;
  }

  return (
    <div className="space-y-6">
      <TermTableToolbar
        table={table}
        globalFilter={globalFilter}
        onGlobalFilterChange={setGlobalFilter}
        cardsCount={cards.length}
        deckId={id}
      />
      <TermTable
        table={table}
        columns={columns}
        expandedRows={expandedRows}
        setExpandedRows={setExpandedRows}
      />
      <TermTablePagination table={table} tableId={tableId} />
    </div>
  );
}
