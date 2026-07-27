"use client";

import { useState } from "react";
import { Download, FileJson, Loader2 } from "lucide-react";
import { exportAccountDataAction } from "@/lib/actions/account";

export function DataExportCard() {
  const [isExporting, setIsExporting] = useState(false);

  async function handleExport() {
    setIsExporting(true);
    try {
      const data = await exportAccountDataAction();
      if (!data) {
        alert("Failed to export account data.");
        return;
      }
      const jsonStr = JSON.stringify(data, null, 2);
      const blob = new Blob([jsonStr], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `pycil-data-export-${new Date().toISOString().split("T")[0]}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert("Error generating export download.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <div className="p-6 rounded-2xl border border-neutral-200 bg-white dark:bg-neutral-900 dark:border-neutral-800 shadow-xs space-y-4">
      <div className="flex items-start gap-3">
        <div className="p-3 rounded-xl bg-purple-50 dark:bg-purple-950/50 text-purple-600 dark:text-purple-400">
          <FileJson className="w-6 h-6" />
        </div>
        <div>
          <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">
            Export Your Account Data
          </h3>
          <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
            Download a full JSON copy of your personal learning history, decks, senses, and FSRS progress.
          </p>
        </div>
      </div>

      <div className="pt-2">
        <button
          type="button"
          disabled={isExporting}
          onClick={handleExport}
          className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-neutral-900 hover:bg-neutral-800 dark:bg-neutral-100 dark:hover:bg-white dark:text-neutral-900 text-white font-medium text-sm transition-colors disabled:opacity-50"
        >
          {isExporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
          Download Data Export (.json)
        </button>
      </div>
    </div>
  );
}
