import { cn } from "@/lib/utils"

/**
 * One large figure with its label.
 *
 * The mono face with tabular figures is the design system's `numeral` token, and the
 * reason is alignment: a row of these has to line up digit for digit, which a
 * proportional face cannot do. This is one of only two screens permitted a figure
 * this size.
 *
 * The optional stage tint borrows the mastery ramp, so a percentage reads as a
 * position on the same scale the rest of the app uses rather than as a bare number in
 * an arbitrary colour.
 */
export function StatFigure({
  label,
  value,
  detail,
  stage,
  className,
}: {
  label: string
  /** Pre-formatted, because a percentage and a count are not formatted alike. */
  value: string
  detail?: string
  /** 1-5. Tints the figure using the mastery ramp. */
  stage?: string
  className?: string
}) {
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <span className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </span>
      <span
        data-stage={stage}
        className={cn("font-mono text-[1.75rem] leading-none tabular-nums", stage && "stage-text")}
      >
        {value}
      </span>
      {detail ? <span className="text-sm text-muted-foreground">{detail}</span> : null}
    </div>
  )
}
