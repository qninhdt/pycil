import { MasteryStage } from "@/components/vocabulary/mastery-stage"
import type { RenderFormat, SingleChoiceReady } from "@/lib/api/types"
import { CheckCircleIcon, XCircleIcon } from "@/lib/icons"
import { masteryStageName } from "@/lib/design/mastery"
import type { Verdict } from "@/lib/study/session-machine"
import { cn } from "@/lib/utils"

import { RevealDisplay } from "./reveal-display"

/**
 * The verdict badge.
 *
 * A wash background with its paired foreground, which is the only sanctioned use
 * of the semantic washes: they are tag and banner backgrounds, never section fills
 * and never bare coloured text. The pairs are contrast-checked as pairs, so using
 * a wash foreground on the page canvas would ship an unverified combination.
 */
function VerdictTag({ isCorrect }: { isCorrect: boolean | null }) {
  const tone =
    isCorrect === true
      ? "bg-wash-success text-on-wash-success"
      : isCorrect === false
        ? "bg-wash-danger text-on-wash-danger"
        // DESIGN.md's neutral tag is `surface-sunken`, which the theme wires to
        // `--muted`. Naming the token directly would reference a class that has
        // no rule.
        : "bg-muted text-muted-foreground"

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium tracking-wide uppercase",
        tone,
      )}
    >
      {isCorrect === true ? (
        <CheckCircleIcon aria-hidden />
      ) : isCorrect === false ? (
        <XCircleIcon aria-hidden />
      ) : null}
      {isCorrect === true ? "Correct" : isCorrect === false ? "Not quite" : "Marked"}
    </span>
  )
}

/**
 * What the server made of an answer.
 *
 * The verdict is the server's, not this component's. It refetches the authoritative
 * question and grades against that, which is why the submission carries only an id
 * and an answer string. Recomputing correctness here from the reveal data would put
 * the answer key in the browser.
 *
 * The mastery change is shown as a named stage transition rather than two numbers.
 * "56 to 61" tells a learner nothing; "Familiar to Applied" is the thing that
 * actually changed, and it only renders when a stage boundary was crossed, so an
 * ordinary correct answer does not fake a promotion.
 */
export function VerdictPanel({
  verdict,
  renderFormat,
  question,
}: {
  verdict: Verdict
  renderFormat: RenderFormat
  question?: SingleChoiceReady
}) {
  // A rubric grade can settle without a boolean, carrying a score and feedback
  // instead. Treating a null as wrong would mark a graded answer incorrect on a
  // technicality, so it reads as neither.
  const isCorrect = verdict.isCorrect

  return (
    <div className="flex flex-col gap-4 border-t border-border pt-4">
      <VerdictTag isCorrect={isCorrect} />

      {/* An announcement rather than a visual change alone: the verdict is the one
          thing on this screen a learner must not miss, and it appears without any
          focus move to carry it to a screen reader. */}
      <span role="status" aria-live="polite" className="sr-only">
        {isCorrect === true
          ? "Correct"
          : isCorrect === false
            ? "Not quite"
            : "Answer marked"}
      </span>

      {verdict.feedback ? (
        <p className="text-sm leading-relaxed text-muted-foreground">
          {verdict.feedback}
        </p>
      ) : null}

      <RevealDisplay
        renderFormat={renderFormat}
        reveal={verdict.reveal}
        question={question}
      />

      <MasteryTransition before={verdict.masteryBefore} after={verdict.masteryAfter} />
    </div>
  )
}

/**
 * The stage change, when there was one.
 *
 * Both scores are needed to say anything: a single score is a position, not a
 * movement. And a move within one band is not a transition worth announcing, so
 * only a crossed boundary renders.
 */
function MasteryTransition({
  before,
  after,
}: {
  before: number | null
  after: number | null
}) {
  if (before == null || after == null) return null

  const from = masteryStageName(before)
  const to = masteryStageName(after)
  if (from === to) return null

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground">{from} to</span>
      <MasteryStage mastery={after} />
    </div>
  )
}
