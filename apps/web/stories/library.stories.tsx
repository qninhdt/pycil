import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { AnonymousReadNotice } from "@/components/library/anonymous-read-notice"
import { NodeRow } from "@/components/library/node-row"
import type { NodeRead } from "@/lib/api/types"

/**
 * Library listing pieces that take plain props: a node row in each of its three
 * kinds, and the read-only notice a signed-out visitor sees on a shared link.
 *
 * `NodeRow` is rendered inside a `<ul>` because it is an `<li>`: showing it bare
 * would validate markup the app never actually ships.
 */
const meta = {
  title: "Library/Listing",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

const deck: NodeRead = {
  id: "1",
  type: "DECK",
  name: "Academic Word List",
  visibility: "PRIVATE",
  itemCount: 240,
}

const folder: NodeRead = {
  id: "2",
  type: "FOLDER",
  name: "IELTS preparation",
  visibility: "PUBLIC",
}

const reference: NodeRead = {
  id: "3",
  type: "REFERENCE",
  name: "Shared: Phrasal verbs",
  visibility: "PRIVATE",
  targetNodeId: "99",
}

const singleWordDeck: NodeRead = {
  id: "4",
  type: "DECK",
  name: "Just one",
  visibility: "PRIVATE",
  itemCount: 1,
}

export const Rows: Story = {
  render: () => (
    <ul className="max-w-md divide-y divide-border">
      <NodeRow node={deck} />
      <NodeRow node={singleWordDeck} />
      <NodeRow node={folder} />
      <NodeRow node={reference} />
    </ul>
  ),
}

/** A public folder carries the globe marker; a private deck does not. */
export const PublicFolder: Story = {
  render: () => (
    <ul className="max-w-md">
      <NodeRow node={folder} />
    </ul>
  ),
}

export const AnonymousRead: Story = {
  render: () => (
    <div className="max-w-md">
      <AnonymousReadNotice />
    </div>
  ),
}
