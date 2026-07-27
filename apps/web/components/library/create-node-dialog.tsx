"use client";

import { useState } from "react";
import { FolderPlus, Layers } from "lucide-react";
import type { NodeType, Visibility } from "@/lib/api/types";
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

interface CreateNodeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parentNodeId?: string | null;
  defaultType?: NodeType;
}

export function CreateNodeDialog({
  open,
  onOpenChange,
  parentNodeId = null,
  defaultType = "FOLDER",
}: CreateNodeDialogProps) {
  const [type, setType] = useState<NodeType>(defaultType);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<Visibility>("PRIVATE");

  const createNode = useCreateNode();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    createNode.mutate(
      {
        type,
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
            {type === "FOLDER" ? (
              <FolderPlus className="h-5 w-5 text-primary" />
            ) : (
              <Layers className="h-5 w-5 text-primary" />
            )}
            Create {type === "FOLDER" ? "Folder" : "Deck"}
          </DialogTitle>
          <DialogDescription>
            Add a new {type.toLowerCase()} to organize your vocabulary learning.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="node-type">Type</Label>
            <NativeSelect
              id="node-type"
              value={type}
              onChange={(e) => setType(e.target.value as NodeType)}
            >
              <option value="FOLDER">Folder</option>
              <option value="DECK">Deck</option>
            </NativeSelect>
          </div>

          <div className="space-y-2">
            <Label htmlFor="node-name">Name *</Label>
            <Input
              id="node-name"
              placeholder={type === "FOLDER" ? "e.g., Business English" : "e.g., Common Verbs"}
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="node-desc">Description (Optional)</Label>
            <Textarea
              id="node-desc"
              placeholder="Brief summary of what's inside..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="node-visibility">Visibility</Label>
            <NativeSelect
              id="node-visibility"
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
              {createNode.isPending ? "Creating..." : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
