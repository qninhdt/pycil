/**
 * Example sentences.
 *
 * Rendered in the serif face by `DefinitionBlock`'s rule rather than this file's:
 * examples are reading material, not interface, so they inherit the reading face
 * from the block that wraps them. This component only handles the list shape.
 *
 * An empty list renders nothing at all. A heading over no examples is worse than
 * silence, because it reads as a loading failure.
 */
export function ExampleList({ examples }: { examples?: string[] | null }) {
  if (!examples || examples.length === 0) return null

  return (
    <ul className="flex flex-col gap-2">
      {examples.map((example, index) => (
        <li
          key={index}
          className="border-l-2 border-border pl-3 font-serif text-sm text-muted-foreground"
        >
          {example}
        </li>
      ))}
    </ul>
  )
}
