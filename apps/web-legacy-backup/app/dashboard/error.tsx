"use client";

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-xl font-semibold">Couldn&apos;t load dashboard</h1>
      <p className="text-sm text-gray-600">
        {error.message || "Something went wrong loading your folders."}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={reset}
          className="rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
        >
          Retry
        </button>
        <a
          href="/"
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
        >
          Go home
        </a>
      </div>
    </main>
  );
}
