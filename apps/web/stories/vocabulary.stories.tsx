import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { CefrChip, TierChip } from "@/components/vocabulary/cefr-chip"
import { ChipList } from "@/components/vocabulary/chip-list"
import { DefinitionBlock } from "@/components/vocabulary/definition-block"
import { DisclosureGroup } from "@/components/vocabulary/disclosure-group"
import { ExampleList } from "@/components/vocabulary/example-list"
import { FormsList } from "@/components/vocabulary/forms-list"
import { Headword } from "@/components/vocabulary/headword"
import { IpaLine } from "@/components/vocabulary/ipa-line"
import { MasteryStage } from "@/components/vocabulary/mastery-stage"
import { RelationList } from "@/components/vocabulary/relation-list"
import { UsageNotes } from "@/components/vocabulary/usage-notes"
import type { SenseForm, SenseRelation } from "@/lib/api/types"

/**
 * The sense-detail components: the two serif surfaces, the mastery ramp, and the
 * dozen optional Lexi fields the `/w/[senseId]` page composes.
 *
 * `Headword` and `DefinitionBlock` are the only two places the serif face is
 * allowed, so their null-word and guideword branches are shown here where a
 * reviewer can see the fallback rather than discovering it on a regenerated sense.
 * The mastery ramp is walked across all five bands plus its two empty inputs. Every
 * list component renders nothing on empty input by design, so a reviewer can confirm
 * the absence reads as intentional rather than as a load failure.
 */
const meta = {
  title: "Vocabulary/Sense Detail",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

export const HeadwordDefault: Story = {
  render: () => (
    <div className="flex flex-col gap-2">
      <Headword word="serendipity" as="h1" className="text-4xl" />
      <DefinitionBlock
        definition="the occurrence of events by chance in a happy or beneficial way"
        guideword="good luck"
      />
    </div>
  ),
}

/** A sense can outlive its headword: the word regenerates away, the row survives. */
export const HeadwordMissing: Story = {
  render: () => (
    <div className="flex flex-col gap-2">
      <Headword word={null} as="h1" className="text-4xl" />
      <DefinitionBlock definition="This definition still renders even with no headword above it." />
    </div>
  ),
}

export const DefinitionWithoutGuideword: Story = {
  render: () => (
    <DefinitionBlock definition="a short parenthetical is optional; without it the definition stands alone" />
  ),
}

/** Every band, so a boundary defect is visible against the ramp beside it. */
export const MasteryRamp: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      <MasteryStage mastery={5} />
      <MasteryStage mastery={20} />
      <MasteryStage mastery={45} />
      <MasteryStage mastery={70} />
      <MasteryStage mastery={95} />
    </div>
  ),
}

/** Server-supplied stage and name win over the local band table. */
export const MasteryServerSupplied: Story = {
  render: () => <MasteryStage stage={4} mastery={60} stageName="Applied" />,
}

/** Nothing to show: both inputs absent renders nothing, not an empty ramp. */
export const MasteryEmpty: Story = {
  render: () => (
    <div className="text-sm text-muted-foreground">
      <MasteryStage />
      (renders nothing when neither stage nor mastery is given)
    </div>
  ),
}

/** CEFR level and content tier: open strings, so an unknown value renders as itself. */
export const Chips: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-2">
      <CefrChip level="B2" />
      <CefrChip level="C1" />
      <TierChip tier="academic" />
      <TierChip tier="general" />
    </div>
  ),
}

export const Pronunciation: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      <IpaLine ipaUk="/ˌser.ənˈdɪp.ə.ti/" ipaUs="/ˌser.ənˈdɪp.ə.t̬i/" />
      {/* One side only: no empty row for the missing region. */}
      <IpaLine ipaUk="/ˈel.ə.kwənt/" />
    </div>
  ),
}

export const Examples: Story = {
  render: () => (
    <ExampleList
      examples={[
        "A fortunate stroke of serendipity brought the two old friends together.",
        "The discovery was pure serendipity, unplanned and unrepeatable.",
      ]}
    />
  ),
}

/** Collocations and grammar labels share this flat chip list. */
export const Chips_Collocations: Story = {
  name: "Collocation Chips",
  render: () => (
    <ChipList items={["by chance", "happy accident", "stroke of luck", "unexpected find"]} />
  ),
}

const forms: SenseForm[] = [
  { inf: "plural", surface: "serendipities" },
  { inf: "adjective", surface: "serendipitous" },
  { inf: "adverb", surface: "serendipitously" },
]

export const InflectedForms: Story = {
  render: () => <FormsList forms={forms} />,
}

export const Usage: Story = {
  render: () => (
    <UsageNotes
      register="formal"
      connotation="positive"
      domain="general"
      usageNote="Most natural describing discoveries or meetings that were unplanned but welcome."
    />
  ),
}

/** Only a usage note, no labels: the labels row is absent, not empty. */
export const UsageNoteOnly: Story = {
  render: () => (
    <UsageNotes usageNote="Often paired with words of discovery; rarely used of deliberate outcomes." />
  ),
}

const relations: SenseRelation[] = [
  {
    relType: "near_synonym",
    toWordId: 1,
    toWordDisplay: "chance",
    toWordStatus: "generated",
    wsdState: "resolved",
    toSenseId: 101,
    toSenseGloss: "the absence of any cause of events that can be predicted",
  },
  {
    relType: "near_synonym",
    toWordId: 2,
    toWordDisplay: "fluke",
    toWordStatus: "generated",
    wsdState: "unresolved",
    toSenseId: null,
  },
  {
    relType: "antonym",
    toWordId: 3,
    toWordDisplay: "design",
    toWordStatus: "pending",
    wsdState: "unresolved",
    toSenseId: null,
  },
]

/** Three target states: a live link, a named-but-unlinked sense, an ungenerated word. */
export const Relations: Story = {
  render: () => <RelationList relations={relations} />,
}

/** The collapsible section the sense page wraps each optional field in. */
export const Disclosure: Story = {
  render: () => (
    <div className="flex max-w-md flex-col">
      <DisclosureGroup title="Inflected forms" hint="3" isEmpty={false}>
        <FormsList forms={forms} />
      </DisclosureGroup>
      <DisclosureGroup title="Usage" isEmpty={false}>
        <UsageNotes register="formal" usageNote="A short note lives here." />
      </DisclosureGroup>
      {/* An empty group renders nothing at all: no heading, no disabled trigger. */}
      <DisclosureGroup title="Never shown" isEmpty>
        <p>unreachable</p>
      </DisclosureGroup>
    </div>
  ),
}
