import { auth, signIn, signOut } from "@/auth";

export default async function HomePage() {
  const session = await auth();

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-between gap-8 p-8">
      <div className="flex flex-1 flex-col items-center justify-center gap-8">
        <div className="text-center">
          <h1 className="text-5xl font-bold tracking-tight">Pycil</h1>
          <p className="mx-auto mt-3 max-w-md text-gray-600">
            AI-generated definitions and questions, ELO-driven spaced
            repetition. Learn vocabulary the way it sticks.
          </p>
        </div>

        <ul className="grid grid-cols-1 gap-3 text-sm text-gray-700 sm:grid-cols-3">
          <li className="rounded border border-gray-200 bg-white p-3">
            <strong className="block">AI definitions</strong>
            Add a word, get a clean POS + CEFR + meaning + examples in
            seconds.
          </li>
          <li className="rounded border border-gray-200 bg-white p-3">
            <strong className="block">ELO scoring</strong>
            Each term builds a strength rating. Hard terms come back sooner.
          </li>
          <li className="rounded border border-gray-200 bg-white p-3">
            <strong className="block">Folders + decks</strong>
            Organize by topic, exam, language. Star and pin what matters.
          </li>
        </ul>

        {session?.user ? (
          <div className="flex flex-col items-center gap-4">
            <p className="text-sm text-gray-700">
              Signed in as <strong>{session.user.email}</strong>
            </p>
            <div className="flex gap-3">
              <a
                href="/dashboard"
                className="rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
              >
                Go to dashboard
              </a>
              <form
                action={async () => {
                  "use server";
                  await signOut({ redirectTo: "/" });
                }}
              >
                <button
                  type="submit"
                  className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
                >
                  Sign out
                </button>
              </form>
            </div>
          </div>
        ) : (
          <form
            action={async () => {
              "use server";
              await signIn("google", { redirectTo: "/dashboard" });
            }}
          >
            <button
              type="submit"
              className="rounded bg-black px-5 py-2.5 text-sm font-medium text-white hover:bg-gray-800"
            >
              Sign in with Google
            </button>
          </form>
        )}
      </div>

      <footer className="flex gap-4 text-xs text-gray-500">
        <a href="/legal/privacy" className="hover:text-gray-900">
          Privacy
        </a>
        <a href="/legal/terms" className="hover:text-gray-900">
          Terms
        </a>
      </footer>
    </main>
  );
}
