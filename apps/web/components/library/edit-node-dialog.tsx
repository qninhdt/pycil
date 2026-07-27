"use client";

import { useState } from "react";
import { Edit } from "lucide-react";
import type { NodeItem } from "@/lib/api/types";
import { useUpdateNode } from "@/lib/query/nodes";
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

interface EditNodeDialogProps {
  node: NodeItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EditNodeDialog({ node, open, onOpenChange }: EditNodeDialogProps) {
  const [prevNodeId, setPrevNodeId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  if (node && node.id !== prevNodeId) {
    setPrevNodeId(node.id);
    setName(node.name);
    setDescription(node.description || "");
  }

  const updateNode = useUpdateNode();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!node || !name.trim()) return;

    updateNode.mutate(
      {
        id: node.id,
        data: {
          name: name.trim(),
          description: description.trim() || null,
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
      }
    );
  };

  if (!node) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Edit className="h-5 w-5 text-primary" />
            Edit {node.type === "FOLDER" ? "Folder" : "Deck"}
          </DialogTitle>
          <DialogDescription>
            Update details for &ldquo;{node.name}&rdquo;.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="edit-name">Name *</Label>
            <Input
              id="edit-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="edit-desc">Description</Label>
            <Textarea
              id="edit-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={updateNode.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || updateNode.isPending}>
              {updateNode.isPending ? "Saving..." : "Save Changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
