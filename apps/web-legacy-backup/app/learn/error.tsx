"use client";

export default function LearnError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main className="mx-auto flex max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-xl font-semibold">Session error</h1>
      <p className="text-sm text-gray-600">
        {error.message || "The study session ran into an issue."}
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
          href="/dashboard"
          className="rounded border border-gray-300 px-4 py-2 text-sm font-medium hover:bg-gray-50"
        >
          Back to dashboard
        </a>
      </div>
    </main>
  );
}
