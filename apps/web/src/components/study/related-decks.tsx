import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import type { NodeRead } from "@/types/domain";

interface RelatedDecksProps {
  relatedDecks: NodeRead[];
}

export function RelatedDecks({ relatedDecks }: RelatedDecksProps) {
  if (relatedDecks.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold">More from this folder</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {relatedDecks.map((relatedDeck) => (
          <Card
            key={relatedDeck.id}
            className="hover:bg-muted/50 transition-colors"
          >
            <Link href={`/decks/${relatedDeck.id}`}>
              <CardHeader>
                <CardTitle className="text-lg">{relatedDeck.name}</CardTitle>
              </CardHeader>
              <CardContent>
                {relatedDeck.description && (
                  <p className="text-sm text-muted-foreground mb-2">
                    {relatedDeck.description}
                  </p>
                )}
                <p className="text-sm text-muted-foreground">
                  {relatedDeck.definition_count} terms
                </p>
              </CardContent>
            </Link>
          </Card>
        ))}
      </div>
    </div>
  );
}
