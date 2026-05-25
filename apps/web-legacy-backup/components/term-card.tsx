"use client";

/**
 * Term card with live enrichment.
 *
 * Server passes `initial` (one row from `GET /decks/{id}/terms`). When the
 * server-rendered state is non-terminal AND a `job_id` exists, the card opens
 * an SSE stream and replaces its body with the streamed result. Otherwise it
 * renders the existing definition immediately.
 */
import { useEffect, useState } from "react";

import type { DeckTermRead, DefinitionRead } from "@/lib/types";
import { useJobStream } from "@/lib/use-job-stream";

interface StreamedDefinition {
  part_of_speech?: string | null;
  cefr_level?: string | null;
  canonical_meaning?: string | null;
  synonyms?: string[] | null;
  antonyms?: string[] | null;
}

interface StreamedPayload {
  definition?: StreamedDefinition;
}

function isStreamedPayload(v: unknown): v is StreamedPayload {
  return !!v && typeof v === "object" && "definition" in (v as object);
}

export function TermCard({ initial }: { initial: DeckTermRead }) {
  const alreadyEnriched = !!initial.definition;
  const isPending =
    !alreadyEnriched &&
    !!initial.job_id &&
    initial.job_status !== "completed" &&
    initial.job_status !== "failed";

  const [streamed, setStreamed] = useState<DefinitionRead | null>(null);
  const stream = useJobStream(isPending ? initial.job_id : null);

  useEffect(() => {
    if (stream.kind === "completed" && isStreamedPayload(stream.result)) {
      const d = stream.result.definition;
      if (d) {
        setStreamed({
          id: 0,
          part_of_speech: d.part_of_speech ?? null,
          cefr_level: d.cefr_level ?? null,
          canonical_meaning: d.canonical_meaning ?? null,
          synonyms: d.synonyms ?? null,
          antonyms: d.antonyms ?? null,
        });
      }
    }
  }, [stream]);

  const def = initial.definition ?? streamed;

  return (
    <li className="rounded border border-gray-200 bg-white p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="font-medium">{initial.term.value}</h3>
        {def?.part_of_speech && (
          <span className="text-xs uppercase text-gray-500">
            {def.part_of_speech}
            {def.cefr_level ? ` · ${def.cefr_level}` : ""}
          </span>
        )}
      </div>

      {def ? (
        <>
          {def.canonical_meaning && (
            <p className="mt-2 text-sm text-gray-700">{def.canonical_meaning}</p>
          )}
          {def.synonyms && def.synonyms.length > 0 && (
            <p className="mt-2 text-xs text-gray-500">
              <span className="font-medium">syn:</span>{" "}
              {def.synonyms.join(", ")}
            </p>
          )}
        </>
      ) : stream.kind === "failed" ? (
        <p className="mt-2 text-sm text-red-600">Failed: {stream.error}</p>
      ) : (
        <p className="mt-2 text-sm text-gray-500">Generating…</p>
      )}
    </li>
  );
}
