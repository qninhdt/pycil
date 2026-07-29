import { Badge } from "@/components/ui/badge"
import type { RenderFormat, Reveal, SingleChoiceReady } from "@/lib/api/types"

/**
 * The answer, disclosed only after grading.
 *
 * Three shapes arrive here, one per grading style: a choice question reveals an
 * index and its option text, a span reveals the accepted text and its variants, a
 * rubric-graded answer reveals only feedback. The wire type carries all of those
 * fields as optional because the contract does not declare which combination
 * arrives, so this narrows by the question's render format rather than by probing
 * fields in an order that happens to work.
 *
 * Display only. Nothing here decides whether the learner was right: that verdict
 * comes from the server, which refetches the authoritative question and grades
 * against it. Reading correctness out of this data would move the answer key into
 * the client, which is the thing the narrow submission contract exists to prevent.
 *
 * The keys are snake_case because the API serialises the dictionary's own reveal
 * dataclass into a bare dict, so nothing aliases them on the way out. See the type
 * for why the OpenAPI document cannot show that.
 */
export function RevealDisplay({
  renderFormat,
  reveal,
  question,
}: {
  renderFormat: RenderFormat
  reveal: Reveal | null
  /** Present for a choice question, so a revealed index can be named. */
  question?: SingleChoiceReady
}) {
  if (!reveal) return null

  switch (renderFormat) {
    case "single_choice": {
      // `correct_option` is preferred over indexing the options: the server already
      // resolved the text, and an index resolved locally would silently drift if the
      // options were ever reordered between delivery and grading.
      const answer =
        reveal.correct_option ??
        (reveal.correct_index != null
          ? question?.payload.options[reveal.correct_index]
          : null)

      if (!answer) return null
      return <RevealRow label="Answer" value={answer} />
    }

    case "text_span": {
      if (!reveal.correct_answer) return null
      return (
        <div className="flex flex-col gap-2">
          <RevealRow label="Answer" value={reveal.correct_answer} />
          {/* Accepted variants matter on a span: a learner who wrote a valid
              inflection and still missed deserves to see that it counted. */}
          {reveal.accepted_forms && reveal.accepted_forms.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-muted-foreground">Also accepted</span>
              {reveal.accepted_forms.map((form) => (
                <Badge key={form} variant="secondary">
                  {form}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
      )
    }

    case "free_text": {
      if (!reveal.feedback) return null
      return <RevealRow label="Notes" value={reveal.feedback} />
    }

    // A flashcard is never graded, so it never carries a reveal.
    case "flashcard":
      return null
  }
}

function RevealRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs tracking-wide text-muted-foreground uppercase">
        {label}
      </span>
      <p className="font-serif leading-relaxed">{value}</p>
    </div>
  )
}
