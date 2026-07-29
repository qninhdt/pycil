import type { FlashcardReady, ReadyQuestion } from "@/lib/api/types"
import { assertNever } from "@/lib/api/types"

import { FreeTextQuestion } from "./free-text-question"
import { SingleChoiceQuestion } from "./single-choice-question"
import { TextSpanQuestion } from "./text-span-question"

/**
 * Every ready question except the exposure card, which has no answer to give.
 *
 * Not exported: the runner narrows on `renderFormat` and reaches this component with
 * an already-specific type, so nothing outside needs the name. Exporting it invited
 * exactly the cast that narrowing makes unnecessary.
 */
type AssessmentQuestion = Exclude<ReadyQuestion, FlashcardReady>

/**
 * Renders the right input for a question's format.
 *
 * The answer is carried as a single string for all three formats because that is
 * what the wire takes: `POST /v1/answers` accepts `answer: string` and nothing else.
 * A choice sends its option index, a span sends the chosen word, free text sends the
 * prose. Keeping one shape here means the runner holds one piece of draft state
 * rather than three that have to be reset in step.
 *
 * A choice sends the index, not the option text. The grader resolves a numeric
 * string as an index before it tries matching option values, so an index is
 * unambiguous while text would misresolve for a question whose options are numbers.
 */
export function QuestionBody({
  question,
  answer,
  onAnswer,
  disabled,
}: {
  question: AssessmentQuestion
  /** Empty string means nothing chosen or typed yet. */
  answer: string
  onAnswer: (next: string) => void
  disabled: boolean
}) {
  switch (question.renderFormat) {
    case "single_choice":
      return (
        <SingleChoiceQuestion
          question={question}
          selected={answer === "" ? null : Number(answer)}
          onSelect={(index) => onAnswer(String(index))}
          disabled={disabled}
        />
      )

    case "text_span":
      return (
        <TextSpanQuestion
          question={question}
          selected={answer === "" ? null : answer}
          onSelect={onAnswer}
          disabled={disabled}
        />
      )

    case "free_text":
      return (
        <FreeTextQuestion question={question} value={answer} onChange={onAnswer} disabled={disabled} />
      )

    default:
      // A fifth render format fails the typecheck here rather than rendering an
      // unanswerable question with no input.
      return assertNever(question)
  }
}
