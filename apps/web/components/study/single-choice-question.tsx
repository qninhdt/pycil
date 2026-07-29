import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import type { SingleChoiceReady } from "@/lib/api/types"
import { cn } from "@/lib/utils"

/**
 * A multiple choice question.
 *
 * The options carry no correct-answer marker: the payload the server sends is
 * answer-free by construction, and the verdict arrives only from grading. So there
 * is nothing here to read the answer out of, which is the point of the design.
 *
 * A real radio group rather than a list of buttons, so a screen reader announces
 * "option 2 of 4" and arrow keys move between choices without any of that being
 * reimplemented. The number badges are labelled decoratively; the option text is
 * the accessible name.
 */
export function SingleChoiceQuestion({
  question,
  selected,
  onSelect,
  disabled,
}: {
  question: SingleChoiceReady
  /** Index into `options`, or null before a choice is made. */
  selected: number | null
  onSelect: (index: number) => void
  disabled: boolean
}) {
  const { stem, options } = question.payload

  return (
    <div className="flex flex-col gap-5">
      <p className="text-lg leading-relaxed">{stem}</p>

      <RadioGroup
        value={selected === null ? null : String(selected)}
        onValueChange={(value) => onSelect(Number(value))}
        disabled={disabled}
        aria-label="Answer options"
      >
        {options.map((option, index) => (
          <label
            key={index}
            className={cn(
              "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border border-border px-3 py-2.5 transition-colors",
              disabled ? "cursor-default" : "hover:bg-muted",
              selected === index && "border-primary bg-muted",
            )}
          >
            <RadioGroupItem value={String(index)} className="mt-1" />
            {/* The digit is a shortcut hint, not content: it duplicates the
                position a screen reader already announces, so it is hidden from
                the accessibility tree rather than read out twice. */}
            <span
              aria-hidden
              className="font-mono text-xs text-muted-foreground tabular-nums"
            >
              {index + 1}
            </span>
            <span className="flex-1 text-sm leading-relaxed">{option}</span>
          </label>
        ))}
      </RadioGroup>
    </div>
  )
}

/**
 * How many options this question has, for the runner's number-key binding.
 *
 * Lives here rather than in the runner so the digit range and the rendered list are
 * read from one place: a key that selects an option that is not on screen is worse
 * than no shortcut at all.
 */
export function choiceCount(question: SingleChoiceReady): number {
  return question.payload.options.length
}
