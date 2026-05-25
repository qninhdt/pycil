"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Languages } from "lucide-react";

const LANGS = [
  { code: "vi", label: "Tiếng Việt" },
  { code: "ja", label: "日本語" },
  { code: "ko", label: "한국어" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "de", label: "Deutsch" },
];

export function TranslationButton({
  definitionId,
}: {
  definitionId: number;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [translation, setTranslation] = useState<{ lang: string; text: string } | null>(null);

  const translate = async (lang: string) => {
    setBusy(lang);
    try {
      const res = await fetch(
        `/api/core/definitions/${definitionId}/translate?lang=${lang}`,
        { method: "POST", credentials: "include" }
      );
      if (!res.ok) return;
      const data = (await res.json()) as {
        cached: boolean;
        translation?: string;
        job_id?: string;
      };
      if (data.translation) {
        setTranslation({ lang, text: data.translation });
      }
    } finally {
      setBusy(null);
      setOpen(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setOpen((o) => !o)}
          title="Translate"
        >
          <Languages className="h-4 w-4" />
        </Button>
        {open
          ? LANGS.map((l) => (
              <Button
                key={l.code}
                variant="outline"
                size="sm"
                onClick={() => translate(l.code)}
                disabled={busy !== null}
              >
                {l.label}
              </Button>
            ))
          : null}
      </div>
      {translation ? (
        <p className="text-sm text-muted-foreground">
          <span className="mr-2 rounded bg-muted px-1.5 py-0.5 text-[10px]">
            {translation.lang}
          </span>
          {translation.text}
        </p>
      ) : null}
    </div>
  );
}
