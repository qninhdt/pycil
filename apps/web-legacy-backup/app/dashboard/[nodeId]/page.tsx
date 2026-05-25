import Link from "next/link";

import { api } from "@/lib/api";
import {
  addTermAction,
  createNodeAction,
  deleteNodeAction,
  togglePinAction,
  toggleStarAction,
} from "@/lib/actions";
import { startSessionAction } from "@/lib/learning-actions";
import type { DeckTermRead, NodeRead } from "@/lib/types";
import { TermCard } from "@/components/term-card";
import { redirect } from "next/navigation";

export default async function NodeDetailPage(props: {
  params: Promise<{ nodeId: string }>;
}) {
  const { nodeId } = await props.params;
  const node = await api<NodeRead>(`/nodes/${nodeId}`);
  const children =
    node.type === "FOLDER"
      ? await api<NodeRead[]>(`/nodes/${nodeId}/children`)
      : [];

  return (
    <main className="mx-auto max-w-5xl p-8">
      <nav className="mb-4 text-sm text-gray-500">
        <Link href="/dashboard" className="hover:underline">
          Dashboard
        </Link>
        {node.breadcrumb.slice(0, -1).map((b) => (
          <span key={b.id}>
            {" / "}
            <Link href={`/dashboard/${b.id}`} className="hover:underline">
              {b.name}
            </Link>
          </span>
        ))}
        <span> / {node.name}</span>
      </nav>

      <header className="mb-6 flex items-start justify-between">
        <div>
          <span className="text-xs uppercase text-gray-500">{node.type}</span>
          <h1 className="text-2xl font-semibold">{node.name}</h1>
          {node.description && (
            <p className="mt-1 text-gray-600">{node.description}</p>
          )}
        </div>
        <div className="flex gap-2">
          <form
            action={async () => {
              "use server";
              await toggleStarAction(node.id);
            }}
          >
            <button className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50">
              {node.is_starred ? "★ Starred" : "☆ Star"}
            </button>
          </form>
          <form
            action={async () => {
              "use server";
              await togglePinAction(node.id);
            }}
          >
            <button className="rounded border border-gray-300 px-3 py-1 text-sm hover:bg-gray-50">
              {node.is_pinned ? "📌 Pinned" : "Pin"}
            </button>
          </form>
          <form
            action={async () => {
              "use server";
              await deleteNodeAction(node.id, node.parent_node_id);
            }}
          >
            <button className="rounded border border-red-300 px-3 py-1 text-sm text-red-600 hover:bg-red-50">
              Delete
            </button>
          </form>
        </div>
      </header>

      {node.type === "FOLDER" ? (
        <FolderView nodeId={node.id} children={children} />
      ) : (
        <DeckView nodeId={node.id} />
      )}
    </main>
  );
}

async function fetchDeckTerms(deckId: string): Promise<DeckTermRead[]> {
  return api<DeckTermRead[]>(`/decks/${deckId}/terms`);
}

function FolderView({
  nodeId,
  children,
}: {
  nodeId: string;
  children: NodeRead[];
}) {
  return (
    <>
      <section className="mb-6">
        <h2 className="mb-3 text-lg font-medium">Add child</h2>
        <form
          action={createNodeAction}
          className="flex flex-wrap gap-2 rounded border border-gray-200 bg-gray-50 p-3"
        >
          <input type="hidden" name="parent_node_id" value={nodeId} />
          <select
            name="type"
            defaultValue="DECK"
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          >
            <option value="FOLDER">Folder</option>
            <option value="DECK">Deck</option>
          </select>
          <input
            name="name"
            placeholder="Name"
            required
            className="flex-1 rounded border border-gray-300 px-3 py-1 text-sm"
          />
          <button className="rounded bg-black px-3 py-1 text-sm font-medium text-white hover:bg-gray-800">
            Create
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Contents</h2>
        {children.length === 0 ? (
          <p className="text-sm text-gray-500">Empty folder.</p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {children.map((c) => (
              <li
                key={c.id}
                className="rounded border border-gray-200 bg-white p-4 hover:border-gray-300"
              >
                <Link href={`/dashboard/${c.id}`} className="block">
                  <span className="text-xs uppercase text-gray-500">
                    {c.type}
                  </span>
                  <h3 className="mt-1 font-medium">{c.name}</h3>
                  <p className="mt-2 text-xs text-gray-400">
                    {c.definition_count} terms
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}

function DeckView({ nodeId }: { nodeId: string }) {
  return (
    <>
      <section className="mb-6 flex justify-end">
        <form
          action={async () => {
            "use server";
            const r = await startSessionAction(nodeId, 20);
            redirect(`/learn/${r.session_id}`);
          }}
        >
          <button className="rounded bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700">
            Study this deck
          </button>
        </form>
      </section>

      <section className="mb-6">
        <h2 className="mb-3 text-lg font-medium">Add term</h2>
        <form
          action={async (fd) => {
            "use server";
            await addTermAction(nodeId, fd);
          }}
          className="flex gap-2 rounded border border-gray-200 bg-gray-50 p-3"
        >
          <input
            name="value"
            placeholder="e.g. ephemeral"
            required
            maxLength={64}
            className="flex-1 rounded border border-gray-300 px-3 py-1 text-sm"
          />
          <button className="rounded bg-black px-3 py-1 text-sm font-medium text-white hover:bg-gray-800">
            Add
          </button>
        </form>
      </section>

      <DeckTerms nodeId={nodeId} />
    </>
  );
}

async function DeckTerms({ nodeId }: { nodeId: string }) {
  const terms = await fetchDeckTerms(nodeId);
  if (terms.length === 0) {
    return (
      <p className="text-sm text-gray-500">
        No terms yet. Add one above to trigger AI enrichment.
      </p>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {terms.map((t) => (
        <TermCard key={t.term.id} initial={t} />
      ))}
    </ul>
  );
}
