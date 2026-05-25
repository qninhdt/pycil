import type { NodeRead } from "@/types/domain";

interface DeckHeaderProps {
  deck: NodeRead;
}

export function DeckHeader({ deck }: DeckHeaderProps) {
  return (
    <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
      <div className="flex-1">
        <h1 className="text-3xl font-bold">{deck.name}</h1>
        {deck.description && (
          <p className="text-muted-foreground mt-1">{deck.description}</p>
        )}
        <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
          <span>{deck.definition_count} terms</span>
          <span>•</span>
          <span>
            Updated {new Date(deck.updated_at).toLocaleDateString()}
          </span>
        </div>
      </div>
    </div>
  );
}
