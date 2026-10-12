import { cn } from "cn"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("shimmer shimmer-bg rounded-none bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
