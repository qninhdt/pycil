import type { SenseForm } from "@/lib/api/types"

/**
 * Inflected forms, as an inflection-to-surface table.
 *
 * A definition list rather than a table element: there are two columns and no
 * header worth reading, and `dl` carries the label/value relationship to a screen
 * reader without a grid's navigation overhead.
 */
export function FormsList({ forms }: { forms: SenseForm[] }) {
  if (forms.length === 0) return null

  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {forms.map((form) => (
        <div key={`${form.inf}-${form.surface}`} className="col-span-2 grid grid-cols-subgrid">
          <dt className="text-muted-foreground">{form.inf}</dt>
          <dd>{form.surface}</dd>
        </div>
      ))}
    </dl>
  )
}
