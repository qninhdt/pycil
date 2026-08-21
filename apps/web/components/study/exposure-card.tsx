import { Button } from "@/components/ui/button"
import { DefinitionBlock } from "@/components/vocabulary/definition-block"
import { ExampleList } from "@/components/vocabulary/example-list"
import { Headword } from "@/components/vocabulary/headword"
import { IpaLine } from "@/components/vocabulary/ipa-line"
import type { FlashcardReady } from "@/lib/api/types"
import { ArrowRightIcon } from "@/lib/icons"

/**
 * A word being introduced, not tested.
 *
 * This is the only card with no answer. Its `questionId` is null because the server
 * never issued an answerable question for it, and posting to `/answers` with a null
 * id is refused — so there is deliberately no submit control here, not a disabled
 * one. The single action moves on.
 *
 * The payload keeps the upstream dictionary's snake_case keys. That is the shape the
 * API passes through verbatim rather than restating, and renaming it here would put
 * a translation layer between two systems that already agree.
 */
export function ExposureCard({
  question,
  onAdvance,
}: {
  question: FlashcardReady
  onAdvance: () => void
}) {
  const { word, definition, pos, example, ipa_uk, ipa_us } = question.payload

  return (
    <div className="flex flex-col gap-6">
      <p className="text-xs tracking-wide text-muted-foreground uppercase">
        New word
      </p>

      <div className="flex flex-col gap-2">
        <Headword word={word} as="h1" className="text-4xl" />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {pos ? <span className="text-sm text-muted-foreground">{pos}</span> : null}
          <IpaLine ipaUk={ipa_uk} ipaUs={ipa_us} />
        </div>
      </div>

      <DefinitionBlock definition={definition} />

      {/* One example arrives as a string where the sense record carries a list, so
          it is wrapped rather than given a second rendering path. */}
      <ExampleList examples={example ? [example] : null} />

      <Button onClick={onAdvance} size="lg" className="self-start">
        Got it
        <ArrowRightIcon data-icon="inline-end" />
      </Button>
    </div>
  )
}
