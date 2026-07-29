import { cn } from "@/lib/utils"

/**
 * The frame every study surface renders inside.
 *
 * No shell chrome. The study route sits outside the app group precisely so that
 * navigation, the header, and the assistant launcher are absent: what is on screen
 * is one question and the two controls that act on it.
 *
 * `min-h-[100dvh]` rather than `h-screen`. On mobile Safari `100vh` is taller than
 * the visible viewport while the address bar is showing, so a full-height study
 * screen would push its own submit button under the browser chrome — exactly the
 * control the learner needs on every question.
 */
export function QuestionStage({
  header,
  footer,
  children,
  className,
}: {
  /** The round indicator and the exit affordance. */
  header?: React.ReactNode
  /** Submit, continue, or whatever advances from here. */
  footer?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <div className="flex min-h-[100dvh] flex-col">
      {header ? (
        <header className="flex items-center justify-between gap-3 px-4 py-3">
          {header}
        </header>
      ) : null}

      {/* The question owns the vertical middle, so it lands in the same place on
          every card and the learner's eye does not have to re-find it. */}
      <main
        className={cn(
          "mx-auto flex w-full max-w-[640px] flex-1 flex-col justify-center gap-6 px-4 py-6",
          className,
        )}
      >
        {children}
      </main>

      {/* Sticky rather than in-flow: on a long free-text question the submit
          control stays reachable without scrolling past the input. */}
      {footer ? (
        <footer className="sticky bottom-0 border-t border-border bg-background/95 backdrop-blur-sm">
          <div className="mx-auto flex w-full max-w-[640px] items-center justify-end gap-3 px-4 py-3">
            {footer}
          </div>
        </footer>
      ) : null}
    </div>
  )
}
