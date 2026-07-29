import { Badge } from "@/components/ui/badge"

/**
 * The four short labels that qualify how a sense is used, plus the prose note.
 *
 * Register, connotation and domain are single words on the wire ("formal",
 * "pejorative", "law"), so they read as labelled chips rather than sentences. The
 * usage note is real prose and gets a paragraph.
 *
 * Each field renders only when present. An absent one leaves no label behind — a
 * sense with no register should not show "Register: —".
 */
export function UsageNotes({
  register,
  connotation,
  domain,
  usageNote,
}: {
  register?: string | null
  connotation?: string | null
  domain?: string | null
  usageNote?: string | null
}) {
  const labels = [
    { label: "Register", value: register },
    { label: "Connotation", value: connotation },
    { label: "Domain", value: domain },
  ].filter((entry) => Boolean(entry.value))

  if (labels.length === 0 && !usageNote) return null

  return (
    <div className="flex flex-col gap-3">
      {labels.length > 0 ? (
        <dl className="flex flex-wrap gap-x-4 gap-y-2">
          {labels.map(({ label, value }) => (
            <div key={label} className="flex items-center gap-2">
              <dt className="text-xs text-muted-foreground">{label}</dt>
              <dd>
                <Badge variant="secondary">{value}</Badge>
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {usageNote ? (
        <p className="text-sm leading-relaxed text-muted-foreground">{usageNote}</p>
      ) : null}
    </div>
  )
}
