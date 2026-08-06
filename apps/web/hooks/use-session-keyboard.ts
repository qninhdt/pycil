"use client"

import { useEffect } from "react"

import { choiceCount } from "@/components/study/single-choice-question"
import { canSubmit, type Phase } from "@/lib/study/session-machine"

/**
 * Operating a study session from the keyboard alone.
 *
 * Bound at the document rather than on each control, and that is the reason this is
 * a hook rather than handlers on the elements: the key that matters most — Enter to
 * submit — has to work while focus sits in the answer input, which is not inside the
 * footer that holds the button.
 *
 * Extracted from the runner because it is the one block there that reads as a
 * separate subject: it takes the phase and four callbacks, returns nothing, and its
 * correctness is entirely about which key means what on which screen.
 */
export function useSessionKeyboard({
  phase,
  answer,
  exiting,
  advanceOnEnter,
  onAdvance,
  onSubmit,
  onAnswer,
  onExit,
}: {
  phase: Phase
  answer: string
  /** True while the exit dialog is open, which takes the keyboard entirely. */
  exiting: boolean
  /**
   * Whether Enter means "carry on" rather than "submit".
   *
   * Computed by the caller because it spans more than the phase: a settled verdict,
   * a grade that will not arrive, an exposure card and a round break all mean the
   * same thing to Enter, and two of those are not phase states.
   */
  advanceOnEnter: boolean
  onAdvance: () => void
  onSubmit: () => void
  onAnswer: (value: string) => void
  onExit: () => void
}) {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.metaKey || event.altKey) return

      // While the exit dialog is open it owns the keyboard entirely. Without this
      // the two fight over the same event: Escape would reach the dialog's own
      // dismiss *and* this handler, which would immediately reopen what was just
      // closed, and Enter would advance the session behind a modal asking whether
      // to leave it.
      if (exiting) return

      if (event.key === "Escape") {
        event.preventDefault()
        onExit()
        return
      }

      if (event.key === "Enter" && advanceOnEnter) {
        event.preventDefault()
        onAdvance()
        return
      }

      if (phase.kind !== "asking") return

      // In a textarea Enter is a newline, so committing free text needs a modifier.
      // Anywhere else a bare Enter submits.
      const inTextarea =
        event.target instanceof HTMLElement && event.target.tagName === "TEXTAREA"
      if (event.key === "Enter" && (!inTextarea || event.ctrlKey)) {
        if (!canSubmit(phase) || answer.trim().length === 0) return
        event.preventDefault()
        onSubmit()
        return
      }

      // Digits select an option, but only where digits are not themselves an answer:
      // typing "1" into a free-text box must stay a character.
      if (
        phase.question.renderFormat === "single_choice" &&
        canSubmit(phase) &&
        /^[1-9]$/.test(event.key)
      ) {
        const index = Number(event.key) - 1
        if (index >= choiceCount(phase.question)) return
        event.preventDefault()
        onAnswer(String(index))
      }
    }

    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [phase, answer, exiting, advanceOnEnter, onAdvance, onSubmit, onAnswer, onExit])
}
