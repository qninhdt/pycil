"use client"

import { use, useEffect, useState } from "react"

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
import type { SenseDetail } from "@/lib/api/types"
import { Spinner } from "@/components/ui/spinner"

export default function SensePage({ params }: { params: Promise<{ senseId: string }> }) {
  const parsed = Number(use(params).senseId)
  const [sense, setSense] = useState<SenseDetail | null | undefined>(undefined)

  useEffect(() => {
    if (!Number.isInteger(parsed)) return
    void readSenseDetail(parsed).then(setSense)
  }, [parsed])

  if (!Number.isInteger(parsed)) return <p className="text-sm text-muted-foreground">This word is not available.</p>
  if (sense === undefined) return <Spinner aria-label="Loading word" />
  if (!sense) return <p className="text-sm text-muted-foreground">This word is not available.</p>

  return (
    <article className="flex flex-col gap-6">
      <header className="flex flex-col gap-2">
        <Headword word={sense.word} as="h1" className="text-3xl" />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {sense.pos ? <span className="text-sm text-muted-foreground">{sense.pos}</span> : null}
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
        <DisclosureGroup title="Inflected forms" hint={countHint(sense.forms?.length)} isEmpty={!sense.forms?.length}>
          <FormsList forms={sense.forms ?? []} />
        </DisclosureGroup>
        <DisclosureGroup title="Collocations" hint={countHint(sense.collocations?.length)} isEmpty={!sense.collocations?.length}>
          <ChipList items={sense.collocations ?? []} />
        </DisclosureGroup>
        <DisclosureGroup title="Grammar" hint={countHint(sense.grammar?.length)} isEmpty={!sense.grammar?.length}>
          <ChipList items={sense.grammar ?? []} />
        </DisclosureGroup>
        <DisclosureGroup
          title="Usage"
          isEmpty={!sense.register && !sense.connotation && !sense.domain && !sense.usageNote}
        >
          <UsageNotes register={sense.register} connotation={sense.connotation} domain={sense.domain} usageNote={sense.usageNote} />
        </DisclosureGroup>
        <DisclosureGroup title="Related words" hint={countHint(sense.relations?.length)} isEmpty={!sense.relations?.length}>
          <RelationList relations={sense.relations ?? []} />
        </DisclosureGroup>
        <DisclosureGroup title="Sources" hint={countHint(sense.references?.length)} isEmpty={!sense.references?.length}>
          <ul className="flex flex-col gap-1.5 text-sm text-muted-foreground">
            {(sense.references ?? []).map((reference) => (
              <li key={`${reference.source}-${reference.sourceRef}`}>
                {reference.source}<span className="font-mono text-xs"> {reference.sourceRef}</span>
              </li>
            ))}
          </ul>
        </DisclosureGroup>
      </div>
    </article>
  )
}

function countHint(length?: number): string | undefined {
  return length ? String(length) : undefined
}
