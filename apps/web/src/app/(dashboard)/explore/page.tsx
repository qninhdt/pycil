"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useRouter } from "next/navigation";
import {
  usePublicDecks,
  useClonePublicDeck,
} from "@/lib/api-hooks/use-public-decks";

export default function ExplorePage() {
  const [q, setQ] = useState("");
  const [submittedQ, setSubmittedQ] = useState("");
  const router = useRouter();

  const { data, isFetching } = usePublicDecks(submittedQ);
  const decks = data?.decks ?? [];
  const cloneDeck = useClonePublicDeck();

  const clone = (deckId: string) => {
    cloneDeck.mutate(deckId, {
      onSuccess: ({ new_deck_id }) => router.push(`/decks/${new_deck_id}`),
    });
  };

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Explore public decks</h1>
        <div className="flex gap-2">
          <Input
            placeholder="Search…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") setSubmittedQ(q);
            }}
            className="w-48"
          />
          <Button onClick={() => setSubmittedQ(q)} disabled={isFetching}>
            Search
          </Button>
        </div>
      </div>

      {decks.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {isFetching ? "Loading…" : "No public decks yet."}
        </p>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {decks.map((d) => (
            <Card key={d.id}>
              <CardHeader>
                <CardTitle className="text-base">{d.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {d.description ? (
                  <p className="text-sm text-muted-foreground line-clamp-3">
                    {d.description}
                  </p>
                ) : null}
                <div className="flex gap-2">
                  <Badge variant="secondary">{d.term_count} terms</Badge>
                  <Badge variant="secondary">{d.clone_count} clones</Badge>
                </div>
                <Button size="sm" onClick={() => clone(d.id)}>
                  Clone to my decks
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
