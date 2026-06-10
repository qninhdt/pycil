"use client";

import { useState } from "react";

import {
  useCreateReport,
} from "@/lib/api-hooks/use-admin-reports";
import type { ReportContentType } from "@/lib/api-client/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Flag } from "lucide-react";

interface ReportDialogProps {
  contentType: ReportContentType;
  contentId: string;
  /** Optional trigger override; defaults to a small "Report" ghost button. */
  trigger?: React.ReactNode;
}

/**
 * Reusable Report button + dialog for public decks and definition comments.
 * Drop in on a public deck page (`contentType="deck"`, deck UUID) or a comment
 * (`contentType="comment"`, comment id) once those surfaces exist.
 */
export function ReportDialog({ contentType, contentId, trigger }: ReportDialogProps) {
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [details, setDetails] = useState("");
  const createReport = useCreateReport();

  const submit = () => {
    createReport.mutate(
      {
        content_type: contentType,
        content_id: contentId,
        reason: reason.trim(),
        details: details.trim() || undefined,
      },
      {
        onSuccess: () => {
          setOpen(false);
          setReason("");
          setDetails("");
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button variant="ghost" size="sm" className="gap-1.5">
            <Flag className="h-4 w-4" />
            Report
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Report this {contentType}</DialogTitle>
          <DialogDescription>
            Tell us what&apos;s wrong. A moderator will review it.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <Input
            placeholder="Reason (e.g. spam, abuse)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            aria-label="Report reason"
            maxLength={200}
          />
          <Input
            placeholder="Optional details"
            value={details}
            onChange={(e) => setDetails(e.target.value)}
            aria-label="Report details"
            maxLength={2000}
          />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={submit}
            disabled={createReport.isPending || reason.trim().length === 0}
          >
            Submit report
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
