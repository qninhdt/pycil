"use client";

import { useState } from "react";
import { Layers } from "lucide-react";
import type { Visibility } from "@/lib/api/types";
import { useCreateNode } from "@/lib/query/nodes";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { NativeSelect } from "@/components/ui/native-select";

interface CreateDeckDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parentNodeId?: string | null;
}

export function CreateDeckDialog({
  open,
  onOpenChange,
  parentNodeId = null,
}: CreateDeckDialogProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");

  const createNode = useCreateNode();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    createNode.mutate(
      {
        type: "DECK",
        name: name.trim(),
        description: description.trim() || null,
        parentNodeId,
        visibility,
      },
      {
        onSuccess: () => {
          setName("");
          setDescription("");
          onOpenChange(false);
        },
      }
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            Create New Deck
          </DialogTitle>
          <DialogDescription>
            Create a vocabulary deck to add words and practice with FSRS spaced repetition.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="deck-name">Deck Name *</Label>
            <Input
              id="deck-name"
              placeholder="e.g., Common Verbs, Academic Vocabulary"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="deck-desc">Description (Optional)</Label>
            <Textarea
              id="deck-desc"
              placeholder="Brief summary of words in this deck..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="deck-visibility">Visibility</Label>
            <NativeSelect
              id="deck-visibility"
              value={visibility}
              onChange={(e) => setVisibility(e.target.value as Visibility)}
            >
              <option value="PRIVATE">Private (Only you)</option>
              <option value="PUBLIC">Public (Accessible via link)</option>
            </NativeSelect>
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={createNode.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || createNode.isPending}>
              {createNode.isPending ? "Creating..." : "Create Deck"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
