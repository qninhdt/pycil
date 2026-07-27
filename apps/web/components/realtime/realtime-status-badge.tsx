"use client";

import { useRealtimeConnectionState } from "@/lib/realtime/provider";
import { Radio } from "lucide-react";

export function RealtimeStatusBadge() {
  const connectionState = useRealtimeConnectionState();
  const isConnected = connectionState === "connected";
  const isConnecting = connectionState === "connecting";
  const label = isConnected
    ? "Realtime connected"
    : isConnecting
      ? "Realtime connecting"
      : "Realtime unavailable";

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all ${
        isConnected
          ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
          : isConnecting
            ? "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400"
            : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
      }`}
    >
      <Radio
        className={`w-3 h-3 ${
          isConnected ? "animate-pulse text-emerald-500" : isConnecting ? "text-blue-500" : "text-amber-500"
        }`}
      />
      <span>{label}</span>
    </div>
  );
}
