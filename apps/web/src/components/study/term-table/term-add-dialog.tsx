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
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Plus, BookOpen, Loader2 } from "lucide-react";
import { useAddTerm } from "@/lib/api-hooks/use-terms";
import { JobStreamWatcher } from "./job-stream-watcher";
import { apiErrorMessage } from "@/lib/api-error-copy";
import type { UUID } from "@/types/domain";

interface TermAddDialogProps {
  deckId: UUID;
  trigger?: React.ReactNode;
}

export function TermAddDialog({ deckId, trigger }: TermAddDialogProps) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [pendingTerm, setPendingTerm] = useState<string | null>(null);
  const addTerm = useAddTerm(deckId);

  useEffect(() => {
    if (!open) {
      setValue("");
      setPendingJobId(null);
      setPendingTerm(null);
    }
  }, [open]);

  const handleSubmit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    try {
      const result = await addTerm.mutateAsync(trimmed);
      setPendingJobId(result.job_id ?? null);
      setPendingTerm(result.term?.value ?? trimmed);
      if (!result.job_id) {
        toast.success(`Added "${trimmed}"`);
        setOpen(false);
      }
    } catch (error) {
      toast.error(apiErrorMessage(error, "Could not add term"));
    }
  };

  const handleCompleted = () => {
    toast.success(`Added "${pendingTerm ?? value}"`);
    setOpen(false);
  };

  const handleFailed = (err: string | null) => {
    toast.error(err ?? "Generation failed");
    setPendingJobId(null);
  };

  const submitting = addTerm.isPending;
  const watching = pendingJobId !== null;

  return (
    <Dialog open={open} onOpenChange={(o) => !watching && setOpen(o)}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button size="default" className="w-full sm:w-auto">
            <Plus className="h-4 w-4" />
            <span className="ml-2">Add Term</span>
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <BookOpen className="h-5 w-5" />
              Add Term to Deck
            </DialogTitle>
            <DialogDescription>
              Type a word or phrase. We will generate definitions for you.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5">
            <Label htmlFor="term-value">Term</Label>
            <Input
              id="term-value"
              name="value"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="loquacious"
              required
              minLength={1}
              maxLength={64}
              autoFocus
              disabled={submitting || watching}
            />
          </div>

          {watching && pendingJobId && (
            <div className="rounded-md border bg-muted/30 p-3">
              <JobStreamWatcher
                jobId={pendingJobId}
                deckId={deckId}
                onCompleted={handleCompleted}
                onFailed={handleFailed}
              />
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={submitting || watching}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={submitting || watching || !value.trim()}
            >
              {(submitting || watching) && (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              )}
              Add term
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
