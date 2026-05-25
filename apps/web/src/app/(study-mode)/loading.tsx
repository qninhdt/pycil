export default function StudyModeLoading() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="space-y-3 w-full max-w-md p-6">
        <div className="h-6 w-1/2 animate-pulse rounded bg-muted" />
        <div className="h-32 animate-pulse rounded bg-muted" />
        <div className="h-12 animate-pulse rounded bg-muted" />
      </div>
    </div>
  );
}
