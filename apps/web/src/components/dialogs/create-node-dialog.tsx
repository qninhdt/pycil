"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateNode } from "@/lib/api-hooks/use-nodes";
import { apiErrorMessage } from "@/lib/api-error-copy";
import type { NodeType, UUID } from "@/types/domain";
import { Folder, FileText, Loader2 } from "lucide-react";

interface CreateNodeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  parentNodeId?: UUID | null;
  defaultType?: NodeType;
  onCreated?: (nodeId: UUID) => void;
}

export function CreateNodeDialog({
  open,
  onOpenChange,
  parentNodeId = null,
  defaultType = "FOLDER",
  onCreated,
}: CreateNodeDialogProps) {
  const [type, setType] = useState<NodeType>(defaultType);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const createNode = useCreateNode();

  useEffect(() => {
    if (open) {
      setType(defaultType);
      setName("");
      setDescription("");
      setSubmitting(false);
    }
  }, [open, defaultType]);

  const handleSubmit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setSubmitting(true);
    try {
      const node = await createNode.mutateAsync({
        type,
        name: trimmed,
        description: description.trim() || null,
        parent_node_id: parentNodeId,
      });
      toast.success(`Created "${node.name}"`);
      onOpenChange(false);
      onCreated?.(node.id);
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not create"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !submitting && onOpenChange(o)}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New {type === "FOLDER" ? "folder" : "deck"}</DialogTitle>
            <DialogDescription>
              {type === "FOLDER"
                ? "Folders organize decks and other folders."
                : "Decks hold terms you want to learn."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <fieldset
              className="grid grid-cols-2 gap-2"
              disabled={submitting}
              aria-label="Node type"
            >
              <label
                className={`flex items-center gap-2 rounded-md border p-3 cursor-pointer transition-colors ${
                  type === "FOLDER"
                    ? "border-primary bg-primary/5"
                    : "hover:bg-muted/50"
                }`}
              >
                <input
                  type="radio"
                  name="node-type"
                  value="FOLDER"
                  checked={type === "FOLDER"}
                  onChange={() => setType("FOLDER")}
                  className="sr-only"
                />
                <Folder className="h-4 w-4" />
                <span className="text-sm font-medium">Folder</span>
              </label>
              <label
                className={`flex items-center gap-2 rounded-md border p-3 cursor-pointer transition-colors ${
                  type === "DECK"
                    ? "border-primary bg-primary/5"
                    : "hover:bg-muted/50"
                }`}
              >
                <input
                  type="radio"
                  name="node-type"
                  value="DECK"
                  checked={type === "DECK"}
                  onChange={() => setType("DECK")}
                  className="sr-only"
                />
                <FileText className="h-4 w-4" />
                <span className="text-sm font-medium">Deck</span>
              </label>
            </fieldset>

            <div className="space-y-1.5">
              <Label htmlFor="node-name">Name</Label>
              <Input
                id="node-name"
                name="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={type === "FOLDER" ? "Verbs" : "Starter Words"}
                required
                minLength={1}
                maxLength={100}
                autoFocus
                disabled={submitting}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="node-description">
                Description{" "}
                <span className="text-xs text-muted-foreground">(optional)</span>
              </Label>
              <Input
                id="node-description"
                name="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                maxLength={500}
                disabled={submitting}
              />
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting || !name.trim()}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Create
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
