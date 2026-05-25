"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { useRouter } from "next/navigation";

type PublicDeck = {
  id: string;
  name: string;
  description: string | null;
  term_count: number;
  clone_count: number;
};

export default function ExplorePage() {
  const [decks, setDecks] = useState<PublicDeck[]>([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const load = async (query: string) => {
    setLoading(true);
    try {
      const url = query
        ? `/api/core/public/decks?q=${encodeURIComponent(query)}`
        : "/api/core/public/decks";
      const res = await fetch(url, { credentials: "include" });
      if (res.ok) {
        const data = (await res.json()) as { decks: PublicDeck[] };
        setDecks(data.decks);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load("");
  }, []);

  const clone = async (deckId: string) => {
    const res = await fetch(`/api/core/public/decks/${deckId}/clone`, {
      method: "POST",
      credentials: "include",
    });
    if (res.ok) {
      const { new_deck_id } = (await res.json()) as { new_deck_id: string };
      router.push(`/decks/${new_deck_id}`);
    }
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
              if (e.key === "Enter") void load(q);
            }}
            className="w-48"
          />
          <Button onClick={() => load(q)} disabled={loading}>
            Search
          </Button>
        </div>
      </div>

      {decks.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {loading ? "Loading…" : "No public decks yet."}
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
