"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

type SearchResult = {
  nodes: { id: string; name: string; type: string; score: number }[];
  terms: { id: number; value: string; score: number }[];
  definitions: {
    id: number;
    term_value: string;
    canonical_meaning: string;
    score: number;
  }[];
};

export function SearchPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult>({
    nodes: [],
    terms: [],
    definitions: [],
  });
  const router = useRouter();

  useEffect(() => {
    if (!open || q.length < 2) {
      setResults({ nodes: [], terms: [], definitions: [] });
      return;
    }
    const id = setTimeout(async () => {
      const res = await fetch(
        `/api/core/search?q=${encodeURIComponent(q)}&limit=8`,
        { credentials: "include" }
      );
      if (res.ok) setResults(await res.json());
    }, 200);
    return () => clearTimeout(id);
  }, [q, open]);

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange}>
      <Command>
        <CommandInput
          placeholder="Search decks, folders, terms…"
          value={q}
          onValueChange={setQ}
        />
        <CommandList>
          <CommandEmpty>
            {q.length < 2 ? "Type at least 2 characters." : "No results."}
          </CommandEmpty>
          {results.nodes.length > 0 ? (
            <CommandGroup heading="Decks & folders">
              {results.nodes.map((n) => (
                <CommandItem
                  key={n.id}
                  onSelect={() => {
                    onOpenChange(false);
                    if (n.type === "DECK") router.push(`/decks/${n.id}`);
                    else router.push(`/u/me/collection?folder=${n.id}`);
                  }}
                >
                  <span className="mr-2 rounded bg-muted px-1.5 py-0.5 text-[10px]">
                    {n.type}
                  </span>
                  {n.name}
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {results.terms.length > 0 ? (
            <CommandGroup heading="Terms">
              {results.terms.map((t) => (
                <CommandItem
                  key={t.id}
                  onSelect={() => {
                    onOpenChange(false);
                  }}
                >
                  {t.value}
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
          {results.definitions.length > 0 ? (
            <CommandGroup heading="Definitions">
              {results.definitions.map((d) => (
                <CommandItem
                  key={d.id}
                  onSelect={() => {
                    onOpenChange(false);
                  }}
                >
                  <span className="font-medium mr-2">{d.term_value}</span>
                  <span className="text-muted-foreground line-clamp-1">
                    {d.canonical_meaning}
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          ) : null}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
