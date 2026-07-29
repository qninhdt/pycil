import { notFound } from "next/navigation"

import { AnonymousReadNotice } from "@/components/library/anonymous-read-notice"
import { CefrChip, TierChip } from "@/components/vocabulary/cefr-chip"
import { ChipList } from "@/components/vocabulary/chip-list"
import { DefinitionBlock } from "@/components/vocabulary/definition-block"
import { DisclosureGroup } from "@/components/vocabulary/disclosure-group"
import { ExampleList } from "@/components/vocabulary/example-list"
import { FormsList } from "@/components/vocabulary/forms-list"
import { Headword } from "@/components/vocabulary/headword"
import { IpaLine } from "@/components/vocabulary/ipa-line"
import { RelationList } from "@/components/vocabulary/relation-list"
import { UsageNotes } from "@/components/vocabulary/usage-notes"
import { readSenseDetail } from "@/lib/actions/library-reads"
import { getSession } from "@/lib/auth/session"

/**
 * The full lexical record for one sense.
 *
 * This is where the cross-repo work pays off: the whole record the dictionary holds,
 * rather than the definition-and-tier the old DTO boundary let through.
 *
 * The reading layer is open and everything else is collapsed. Rendering a dozen
 * optional fields at once turns the page into a field dump, and dropping them throws
 * away the record; a closed group keeps both. A field with no value renders nothing
 * at all, not an empty label, so the page length tracks what is actually known.
 *
 * There is no mastery or schedule block here, for anyone. The sense read returns
 * dictionary content only — progress is per deck, so it lives on a deck row where
 * the deck is known. An anonymous reader is therefore missing nothing on this
 * screen except the ability to add the word somewhere.
 */
export default async function SensePage({
  params,
}: {
  params: Promise<{ senseId: string }>
}) {
  const { senseId } = await params

  // A non-numeric id is not a lookup worth making: sense ids are integers, so
  // anything else is a malformed link rather than a missing sense.
  const parsed = Number(senseId)
  if (!Number.isInteger(parsed)) notFound()

  const [sense, session] = await Promise.all([readSenseDetail(parsed), getSession()])

  // Unknown, in no deck, and in no deck this caller can read all arrive as one 404,
  // so that the endpoint cannot be used to discover which senses exist.
  if (!sense) notFound()

  return (
    <article className="flex flex-col gap-6">
      {!session.isLoggedIn ? <AnonymousReadNotice /> : null}

      <header className="flex flex-col gap-2">
        <Headword word={sense.word} as="h1" className="text-3xl" />

        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {sense.pos ? (
            <span className="text-sm text-muted-foreground">{sense.pos}</span>
          ) : null}
          <CefrChip level={sense.cefrLevel} />
          <TierChip tier={sense.tier} />
        </div>

        <IpaLine ipaUk={sense.ipaUk} ipaUs={sense.ipaUs} />
      </header>

      <div className="flex max-w-[65ch] flex-col gap-4">
        <DefinitionBlock definition={sense.definition} guideword={sense.guideword} />
        <ExampleList examples={sense.examples} />
      </div>

      <div className="flex flex-col">
        <DisclosureGroup
          title="Inflected forms"
          hint={countHint(sense.forms?.length)}
          isEmpty={!sense.forms?.length}
        >
          <FormsList forms={sense.forms ?? []} />
        </DisclosureGroup>

        <DisclosureGroup
          title="Collocations"
          hint={countHint(sense.collocations?.length)}
          isEmpty={!sense.collocations?.length}
        >
          <ChipList items={sense.collocations ?? []} />
        </DisclosureGroup>

        <DisclosureGroup
          title="Grammar"
          hint={countHint(sense.grammar?.length)}
          isEmpty={!sense.grammar?.length}
        >
          <ChipList items={sense.grammar ?? []} />
        </DisclosureGroup>

        {/* One group for four separate fields: register, connotation, domain and the
            usage note are all "how this word lands" rather than what it means, and
            four collapsed headers for four short strings is worse than one. */}
        <DisclosureGroup
          title="Usage"
          isEmpty={
            !sense.register && !sense.connotation && !sense.domain && !sense.usageNote
          }
        >
          <UsageNotes
            register={sense.register}
            connotation={sense.connotation}
            domain={sense.domain}
            usageNote={sense.usageNote}
          />
        </DisclosureGroup>

        <DisclosureGroup
          title="Related words"
          hint={countHint(sense.relations?.length)}
          isEmpty={!sense.relations?.length}
        >
          <RelationList relations={sense.relations ?? []} />
        </DisclosureGroup>

        <DisclosureGroup
          title="Sources"
          hint={countHint(sense.references?.length)}
          isEmpty={!sense.references?.length}
        >
          <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
            {(sense.references ?? []).map((reference) => (
              <li key={`${reference.source}-${reference.sourceRef}`}>
                {reference.source}
                <span className="font-mono text-xs"> {reference.sourceRef}</span>
              </li>
            ))}
          </ul>
        </DisclosureGroup>
      </div>
    </article>
  )
}

/** The count beside a group title, omitted when there is nothing to count. */
function countHint(length?: number): string | undefined {
  return length ? String(length) : undefined
}
