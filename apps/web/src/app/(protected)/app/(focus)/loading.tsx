import { Skeleton } from '@/components/ui/skeleton'

export default function FocusLoading() {
  return (
    <main className="h-svh max-h-svh overflow-hidden flex flex-col bg-background text-foreground animate-in fade-in duration-150" role="status" aria-label="Preparing study session">
      {/* Focus Header */}
      <header className="flex-none h-[78px] flex items-center justify-between px-6 border-b border-foreground max-[760px]:h-16">
        <Skeleton className="size-10" />
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-8 w-20" />
      </header>

      {/* Centered Flashcard / Quiz Area */}
      <section className="flex-1 min-h-0 flex flex-col items-center justify-center p-8">
        <div className="w-full max-w-[680px] flex flex-col items-start gap-6 border border-foreground p-8 sm:p-12">
          <Skeleton className="h-5 w-24" />
          <Skeleton className="h-12 w-3/4" />
          <Skeleton className="h-6 w-full" />
          <Skeleton className="h-6 w-4/5" />
          <div className="w-full flex items-center justify-between pt-8 border-t border-border mt-4">
            <Skeleton className="h-10 w-28" />
            <Skeleton className="h-10 w-32" />
          </div>
        </div>
      </section>
      <span className="sr-only">Preparing study materials...</span>
    </main>
  )
}
