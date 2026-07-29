import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { Viewer } from "@/lib/api/types"

/**
 * Who is signed in.
 *
 * Read-only, and it says why rather than showing disabled inputs. The identity comes
 * from Google and the API has no profile write at all, so an edit form here would be a
 * control that cannot succeed. Stating where the name and picture come from tells the
 * learner where to change them.
 */
export function ProfileCard({ viewer }: { viewer: Viewer }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Account</CardTitle>
        <CardDescription>
          Your name and picture come from your Google account. Changing them there
          changes them here on your next sign-in.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-4">
        <Avatar className="size-12">
          {viewer.image ? <AvatarImage src={viewer.image} alt="" /> : null}
          {/* Always present, because an image can fail to load and an avatar with no
              fallback collapses to an empty circle. */}
          <AvatarFallback>{initial(viewer)}</AvatarFallback>
        </Avatar>

        <div className="flex min-w-0 flex-col">
          {viewer.name ? <span className="font-medium">{viewer.name}</span> : null}
          <span className="truncate text-sm text-muted-foreground">{viewer.email}</span>
        </div>
      </CardContent>
    </Card>
  )
}

/** The name's first letter, or the email's when there is no name. */
function initial(viewer: Viewer): string {
  const source = viewer.name?.trim() || viewer.email
  return source.slice(0, 1).toUpperCase()
}
