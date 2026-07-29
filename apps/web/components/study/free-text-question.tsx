import { Textarea } from "@/components/ui/textarea"
import type { FreeTextReady } from "@/lib/api/types"

/**
 * An open answer, graded by a rubric rather than a rule.
 *
 * This is the only format whose grade does not settle in the response: the server
 * returns a task id and the verdict arrives later. So the submit control here hands
 * off to a pending state rather than to a verdict, and the learner is told that
 * rather than left watching a spinner.
 *
 * The budget matches the server's own limit exactly. `AnswerRequest.answer` is
 * `max_length=10_000`, so a longer answer is rejected after the learner has written
 * it — better to stop the input at the same number than to explain the loss
 * afterwards.
 */
export const ANSWER_MAX_LENGTH = 10_000

export function FreeTextQuestion({
  question,
  value,
  onChange,
  disabled,
}: {
  question: FreeTextReady
  value: string
  onChange: (next: string) => void
  disabled: boolean
}) {
  const remaining = ANSWER_MAX_LENGTH - value.length

  return (
    <div className="flex flex-col gap-5">
      <p className="text-lg leading-relaxed">{question.payload.prompt}</p>

      <div className="flex flex-col gap-2">
        <Textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          maxLength={ANSWER_MAX_LENGTH}
          rows={5}
          aria-label="Your answer"
          placeholder="Write your answer"
        />

        {/* Shown only as the limit comes into range. A counter on an empty field
            reads as a length requirement, which this is not. */}
        {remaining <= 500 ? (
          <p className="text-xs text-muted-foreground tabular-nums" role="status">
            {remaining} characters left
          </p>
        ) : null}
      </div>
    </div>
  )
}
