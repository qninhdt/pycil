"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-2xl font-semibold">Something went wrong</h1>
      <p className="text-sm text-gray-600">
        {error.message || "An unexpected error occurred."}
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
