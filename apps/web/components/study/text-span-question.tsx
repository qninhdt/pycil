import { Input } from "@/components/ui/input"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import type { TextSpanReady } from "@/lib/api/types"

/**
 * A gap-fill question, answered either from a word bank or from memory.
 *
 * The stem arrives with the blank already marked by the dictionary, so it is
 * rendered as given rather than reconstructed from a template here. Splitting it
 * client-side would put a second parser between two systems that already agree on
 * the shape.
 *
 * **There are two modes, and both have to be rendered.** The generator decides which
 * by whether it sends a word bank: `lexi_ai/questions/types/cloze.py` fills
 * `word_bank` only at difficulty 2 and deliberately leaves it empty at difficulty 3,
 * because recognising a word among four is an easier task than recalling it unaided.
 * The payload carries `accepted_forms` for exactly that reason — the grader is built
 * to match typed inflections, not just an exact bank value.
 *
 * Rendering only the bank made every difficulty-3 cloze unanswerable: the toggle
 * group came out empty, no other input existed, and `Submit` stayed disabled with no
 * way to enable it. The learner saw a question and had no means of answering it, and
 * because level 3 is only requested for senses with accumulated mastery, it hit
 * long-standing users mid-session rather than showing up in a first run.
 *
 * The answer is a single string in both modes, which is what `POST /v1/answers`
 * takes: the chosen word, or the typed one.
 */
export function TextSpanQuestion({
  question,
  selected,
  onSelect,
  disabled,
}: {
  question: TextSpanReady
  /** The chosen or typed word, or null before an answer is given. */
  selected: string | null
  onSelect: (word: string) => void
  disabled: boolean
}) {
  const { stem_with_blank, word_bank } = question.payload

  // An empty bank is the generator saying "recall this", not a payload that failed to
  // build. Treating it as a missing bank and rendering nothing is what broke this.
  const fromMemory = word_bank.length === 0

  return (
    <div className="flex flex-col gap-5">
      <p className="text-lg leading-relaxed">{stem_with_blank}</p>

      {fromMemory ? (
        <div className="flex flex-col gap-2">
          {/* A single-line input, because the answer is one word. A textarea would
              invite a sentence and then fail grading, which compares against the
              sense's own surface forms. */}
          <Input
            value={selected ?? ""}
            onChange={(event) => onSelect(event.target.value)}
            disabled={disabled}
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            // Named for what it asks rather than "Your answer", which is the
            // free-text format's label. Two formats sharing one accessible name
            // makes them indistinguishable to a screen reader and to a test.
            aria-label="The missing word"
            placeholder="Type the missing word"
            className="max-w-xs"
          />
          {/* Stated once, plainly: the learner has no bank to infer the expected
              shape from, so the grader's tolerance is worth saying out loud. */}
          <p className="text-xs text-muted-foreground">
            Any correct form of the word is accepted.
          </p>
        </div>
      ) : (
        /* Single select is this primitive's default, so picking a second word
           replaces the first rather than accumulating — which matches the server
           taking exactly one answer string. The value is still an array because
           the primitive models selection uniformly for both modes. */
        <ToggleGroup
          value={selected === null ? [] : [selected]}
          onValueChange={(value) => {
            const next = value[0]
            // An empty array means the learner deselected. There is no "no answer"
            // to submit, so the previous choice stands until another replaces it.
            if (typeof next === "string") onSelect(next)
          }}
          disabled={disabled}
          variant="outline"
          className="flex-wrap"
          aria-label="Word bank"
        >
          {word_bank.map((word) => (
            <ToggleGroupItem key={word} value={word} className="min-h-11">
              {word}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      )}
    </div>
  )
}
