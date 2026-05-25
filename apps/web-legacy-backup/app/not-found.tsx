export default function NotFound() {
  return (
    <main className="mx-auto flex min-h-[60vh] max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-sm text-gray-600">
        The page you&apos;re looking for doesn&apos;t exist.
      </p>
      <a
        href="/"
        className="rounded bg-black px-4 py-2 text-sm font-medium text-white hover:bg-gray-800"
      >
        Go home
      </a>
    </main>
  );
}
