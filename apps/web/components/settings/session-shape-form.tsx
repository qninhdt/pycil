"use client"

import { useState, useTransition } from "react"

import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { toast } from "@/components/ui/toast"
import { updateLearningSettings } from "@/lib/actions/learning-settings"
import { classifyErrorCode } from "@/lib/api/error-taxonomy"
import type { LearningSettings } from "@/lib/api/types"

/**
 * How the learner's sessions are shaped.
 *
 * One form for the whole account, because that is where the API stores it. It used to
 * be per deck, which meant the same person got a different session length depending on
 * which deck they opened, and a session started on a folder ignored the setting
 * entirely — so a configured value applied about half the time.
 *
 * The bounds match the API's own validation and the table's CHECK constraints, so an
 * out-of-range value is refused here with a sentence rather than sent and rejected with
 * a code.
 */
const MIN = 1
const MAX = 100

export function SessionShapeForm({ settings }: { settings: LearningSettings }) {
  const [words, setWords] = useState(String(settings.targetWordsPerSession))
  const [perRound, setPerRound] = useState(String(settings.maxQuestionsPerRound))
  // What the server last confirmed, so "nothing to save" is judged against the server
  // rather than against the values this form was first rendered with.
  const [saved, setSaved] = useState(settings)
  const [problem, setProblem] = useState<string | null>(null)
  const [isSaving, startSaving] = useTransition()

  const wordsValue = Number(words)
  const perRoundValue = Number(perRound)
  const wordsInvalid = !isWithinBounds(wordsValue)
  const perRoundInvalid = !isWithinBounds(perRoundValue)

  const unchanged =
    wordsValue === saved.targetWordsPerSession &&
    perRoundValue === saved.maxQuestionsPerRound

  function submit() {
    setProblem(null)

    startSaving(async () => {
      const result = await updateLearningSettings({
        targetWordsPerSession: wordsValue,
        maxQuestionsPerRound: perRoundValue,
      })

      if (!result.success) {
        setProblem(classifyErrorCode(result.code).message)
        return
      }

      // Re-seeded from the response rather than from what was typed: the server is what
      // the next session reads, and showing anything else would be a guess.
      setWords(String(result.data.targetWordsPerSession))
      setPerRound(String(result.data.maxQuestionsPerRound))
      setSaved(result.data)
      toast.add({ title: "Session settings saved" })
    })
  }

  return (
    <FieldGroup>
      <Field data-invalid={wordsInvalid || undefined}>
        <FieldLabel htmlFor="target-words">Words per session</FieldLabel>
        <Input
          id="target-words"
          type="number"
          inputMode="numeric"
          min={MIN}
          max={MAX}
          value={words}
          aria-invalid={wordsInvalid || undefined}
          onChange={(event) => setWords(event.target.value)}
        />
        <FieldDescription>
          How many words a session tries to cover, mixing what is due with what is new.
        </FieldDescription>
        {wordsInvalid ? (
          <FieldError>Pick a number from {MIN} to {MAX}.</FieldError>
        ) : null}
      </Field>

      <Field data-invalid={perRoundInvalid || undefined}>
        <FieldLabel htmlFor="max-per-round">Questions per round</FieldLabel>
        <Input
          id="max-per-round"
          type="number"
          inputMode="numeric"
          min={MIN}
          max={MAX}
          value={perRound}
          aria-invalid={perRoundInvalid || undefined}
          onChange={(event) => setPerRound(event.target.value)}
        />
        <FieldDescription>
          How many questions a round holds before the session offers a break.
        </FieldDescription>
        {perRoundInvalid ? (
          <FieldError>Pick a number from {MIN} to {MAX}.</FieldError>
        ) : null}
      </Field>

      {problem ? <FieldDescription>{problem}</FieldDescription> : null}

      <Field orientation="horizontal">
        <Button
          onClick={submit}
          disabled={isSaving || wordsInvalid || perRoundInvalid || unchanged}
          size="sm"
        >
          Save
        </Button>
        {/* Stated rather than implied: a live session carries the plan it was created
            with, so a change made mid-session does not alter the session in progress. */}
        <FieldDescription>Applies from your next session.</FieldDescription>
      </Field>
    </FieldGroup>
  )
}

function isWithinBounds(value: number): boolean {
  return Number.isInteger(value) && value >= MIN && value <= MAX
}
