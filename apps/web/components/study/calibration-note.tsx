import { WarningCircleIcon } from "@/lib/icons"

/**
 * Why this question is the difficulty it is.
 *
 * No raw level number reaches the learner. "Level 3 of 4" is a number about the
 * question, not about them, and it invites the reading that a level 1 answer is
 * worth less — which is not how the schedule works.
 *
 * The fallback case is the one that matters. When the requested difficulty had no
 * question available the server serves an easier one, and the attempt is then
 * recorded as a miss whatever the learner answers: the backend treats a fallback
 * delivery as a disqualifier and applies the lower grade. Staying silent about that
 * would show a correct answer that quietly counted against them, which is the
 * fastest way to make someone stop trusting the app. So it is stated plainly,
 * before they answer.
 */
export function CalibrationNote({
  requestedLevel,
  servedLevel,
  isFallback,
}: {
  requestedLevel: number
  servedLevel: number
  isFallback: boolean
}) {
  if (!isFallback) return null

  // `isFallback` is the server's own verdict, so the note follows it rather than
  // re-deriving the comparison. The levels are read only to tell "easier" from
  // "different", and an equal pair still means a substitution happened.
  const easier = servedLevel < requestedLevel

  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-lg bg-muted px-3 py-2 text-xs text-muted-foreground"
    >
      <WarningCircleIcon className="mt-px shrink-0" />
      <span>
        {easier
          ? "A simpler question was available, so that is what you got. This one counts as a miss either way, and the word comes back later."
          : "A substitute question was served for this word. It counts as a miss either way, and the word comes back later."}
      </span>
    </p>
  )
}
