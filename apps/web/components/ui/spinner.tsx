import { cn } from "@/lib/utils"
import { CircleNotchIcon } from "@/lib/icons"

function Spinner({ className, ...props }: React.ComponentProps<"svg">) {
  return (
    <CircleNotchIcon data-slot="spinner" role="status" aria-label="Loading" className={cn("size-4 animate-spin", className)} {...props} />
  )
}

export { Spinner }
