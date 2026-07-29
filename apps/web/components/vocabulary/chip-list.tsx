import { Badge } from "@/components/ui/badge"

/**
 * A plain list of short strings, rendered as chips.
 *
 * Serves collocations and grammar labels alike: both are flat string arrays whose
 * items are read individually rather than as prose, and both come from the same
 * upstream record. One component rather than two identical ones.
 */
export function ChipList({ items }: { items: string[] }) {
  if (items.length === 0) return null

  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item}>
          <Badge variant="outline">{item}</Badge>
        </li>
      ))}
    </ul>
  )
}
