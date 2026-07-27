"use client";

import { useState } from "react";
import { Settings, Save } from "lucide-react";
import { updateDeckSettingsAction } from "@/lib/actions/content";
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
import { toast } from "sonner";

interface DeckSettingsDialogProps {
  nodeId: string;
  deckName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeckSettingsDialog({
  nodeId,
  deckName,
  open,
  onOpenChange,
}: DeckSettingsDialogProps) {
  const [newPerBatch, setNewPerBatch] = useState(10);
  const [reviewPerBatch, setReviewPerBatch] = useState(20);
  const [isSaving, setIsSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await updateDeckSettingsAction(nodeId, {
        newPerBatch,
        reviewPerBatch,
      });
      toast.success("Deck settings saved successfully");
      onOpenChange(false);
    } catch (err: unknown) {
      console.error("Failed to save deck settings:", err);
      toast.error("Failed to update deck settings");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-primary" />
            Cài đặt phiên học bộ từ
          </DialogTitle>
          <DialogDescription>
            Điều chỉnh số lượng từ mới và từ ôn tập mỗi phiên học cho &ldquo;{deckName}&rdquo;.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="new-per-batch">Từ mới mỗi phiên học</Label>
            <Input
              id="new-per-batch"
              type="number"
              min={1}
              max={50}
              value={newPerBatch}
              onChange={(e) => setNewPerBatch(parseInt(e.target.value, 10) || 10)}
              required
            />
            <p className="text-xs text-muted-foreground">
              Số lượng từ mới hệ thống FSRS sẽ đưa vào phiên học (mặc định: 10).
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="review-per-batch">Từ ôn tập mỗi phiên học</Label>
            <Input
              id="review-per-batch"
              type="number"
              min={1}
              max={100}
              value={reviewPerBatch}
              onChange={(e) => setReviewPerBatch(parseInt(e.target.value, 10) || 20)}
              required
            />
            <p className="text-xs text-muted-foreground">
              Số lượng từ cũ cần đến hạn ôn tập được tối ưu theo FSRS 4.5 (mặc định: 20).
            </p>
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isSaving}
            >
              Hủy
            </Button>
            <Button type="submit" disabled={isSaving} className="gap-1.5">
              <Save className="w-4 h-4" />
              <span>{isSaving ? "Đang lưu..." : "Lưu cài đặt"}</span>
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
