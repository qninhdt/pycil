"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Volume2, Loader2 } from "lucide-react";

export function TtsPlayButton({
  definitionId,
  lang = "en",
}: {
  definitionId: number;
  lang?: string;
}) {
  const [busy, setBusy] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const play = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await fetch(
        `/api/core/definitions/${definitionId}/tts?lang=${lang}`,
        { method: "POST", credentials: "include" }
      );
      if (!res.ok) return;
      const data = (await res.json()) as { cached: boolean; url?: string };
      if (data.url) {
        if (!audioRef.current) audioRef.current = new Audio(data.url);
        else audioRef.current.src = data.url;
        await audioRef.current.play();
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button variant="ghost" size="sm" onClick={play} disabled={busy} title="Play TTS">
      {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
    </Button>
  );
}
