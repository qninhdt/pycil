import { CreateNodeSheet } from "@/components/library/create-node-sheet"
import { NodeList } from "@/components/library/node-list"
import { readNodeChildren } from "@/lib/actions/library-reads"
import { getSession } from "@/lib/auth/session"

export const metadata = { title: "Library" }

/**
 * The root of the learner's tree.
 *
 * Anonymous visitors reach this route — the guard leaves it open so a shared link
 * into a deck below it works — but the API has no anonymous listing, and that is
 * deliberate: a public item is reachable by direct link and appears in nobody
 * else's library. So a signed-out visitor is told what this screen is rather than
 * shown an empty tree that implies they have one.
 */
export default async function LibraryPage() {
  const session = await getSession()
  const { items } = await readNodeChildren(null)

  if (!session.isLoggedIn) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <p className="max-w-[65ch] text-sm text-muted-foreground">
          Your library holds the folders and decks you build. Sign in to see yours.
          A deck someone shared with you opens from its own link without an account.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <CreateNodeSheet parentNodeId={null} />
      </div>

      <NodeList
        nodes={items}
        emptyAction={<CreateNodeSheet parentNodeId={null} />}
      />
    </div>
  )
}
