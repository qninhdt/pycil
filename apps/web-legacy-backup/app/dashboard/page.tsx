import { auth, signOut } from "@/auth";
import { api } from "@/lib/api";
import { createNodeAction, ensureOnboardingSeed } from "@/lib/actions";
import type { NodeRead } from "@/lib/types";

export default async function DashboardPage() {
  const session = await auth();
  await ensureOnboardingSeed();
  const nodes = await api<NodeRead[]>("/nodes");

  return (
    <main className="mx-auto max-w-5xl p-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-gray-500">
            {session?.user?.email}
          </p>
        </div>
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/" });
          }}
        >
          <button className="text-sm text-gray-600 hover:text-gray-900">
            Sign out
          </button>
        </form>
      </header>

      <section className="mb-6">
        <h2 className="mb-3 text-lg font-medium">Create</h2>
        <form
          action={createNodeAction}
          className="flex flex-wrap gap-2 rounded border border-gray-200 bg-gray-50 p-3"
        >
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
          <button
            type="submit"
            className="rounded bg-black px-3 py-1 text-sm font-medium text-white hover:bg-gray-800"
          >
            Create
          </button>
        </form>
      </section>

      <section>
        <h2 className="mb-3 text-lg font-medium">Your folders & decks</h2>
        {nodes.length === 0 ? (
          <p className="text-sm text-gray-500">
            Nothing yet. Create your first folder or deck above.
          </p>
        ) : (
          <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {nodes.map((n) => (
              <li
                key={n.id}
                className="rounded border border-gray-200 bg-white p-4 hover:border-gray-300"
              >
                <a href={`/dashboard/${n.id}`} className="block">
                  <div className="flex items-center justify-between">
                    <span className="text-xs uppercase text-gray-500">
                      {n.type}
                    </span>
                    {n.is_pinned && (
                      <span className="text-xs text-amber-600">pinned</span>
                    )}
                  </div>
                  <h3 className="mt-1 font-medium">{n.name}</h3>
                  {n.description && (
                    <p className="mt-1 text-sm text-gray-600">
                      {n.description}
                    </p>
                  )}
                  <p className="mt-2 text-xs text-gray-400">
                    {n.definition_count} terms
                  </p>
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
