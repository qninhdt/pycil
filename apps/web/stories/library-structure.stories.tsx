import type { Meta, StoryObj } from "@storybook/nextjs-vite"

import { NodeBreadcrumb } from "@/components/library/node-breadcrumb"
import { NodeIcon, nodeTypeLabel } from "@/components/library/node-icon"
import type { NodeAncestor, NodeType } from "@/lib/api/types"

/**
 * The library's navigation pieces: the breadcrumb trail and the per-kind glyph.
 *
 * The breadcrumb's load-bearing case is the truncated trail. The API returns only
 * the ancestors a caller may read, so a public deck inside a private folder arrives
 * with its parent hidden; the ellipsis story is what proves that reads as "something
 * is above this you cannot see" rather than as a deck sitting at the root.
 */
const meta = {
  title: "Library/Structure",
  parameters: { layout: "padded" },
} satisfies Meta

export default meta
type Story = StoryObj<typeof meta>

const path: NodeAncestor[] = [
  { id: "1", name: "IELTS preparation", type: "FOLDER" },
  { id: "2", name: "Writing", type: "FOLDER" },
]

export const Breadcrumb: Story = {
  render: () => <NodeBreadcrumb path={path} current="Academic Word List" />,
}

/** At the root: just Library and the node, no separator chain. */
export const BreadcrumbAtRoot: Story = {
  render: () => <NodeBreadcrumb path={[]} current="Standalone deck" />,
}

/** Hidden ancestors: the ellipsis stands in for the part this viewer cannot read. */
export const BreadcrumbTruncated: Story = {
  render: () => (
    <NodeBreadcrumb
      path={[{ id: "2", name: "Writing", type: "FOLDER" }]}
      current="Shared deck"
      hasHiddenAncestors
    />
  ),
}

const kinds: NodeType[] = ["FOLDER", "DECK", "REFERENCE"]

export const Icons: Story = {
  render: () => (
    <ul className="flex flex-col gap-3">
      {kinds.map((type) => (
        <li key={type} className="flex items-center gap-3 text-sm">
          <span className="text-muted-foreground">
            <NodeIcon type={type} />
          </span>
          {nodeTypeLabel(type)}
        </li>
      ))}
    </ul>
  ),
}
