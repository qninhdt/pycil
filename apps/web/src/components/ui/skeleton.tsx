import { cn } from "cn"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "rounded-none bg-[var(--palette-border,#BDC3C7)]/45 dark:bg-[var(--palette-ink-soft,#333333)]/60 animate-pulse border border-foreground/10",
        className
      )}
      {...props}
    />
  )
}

export { Skeleton }
