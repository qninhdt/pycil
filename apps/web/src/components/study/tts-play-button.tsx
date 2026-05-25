"use client";

import { useState } from "react";
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
  const [audio, setAudio] = useState<HTMLAudioElement | null>(null);

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
        const a = audio ?? new Audio(data.url);
        if (!audio) setAudio(a);
        else a.src = data.url;
        await a.play();
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
