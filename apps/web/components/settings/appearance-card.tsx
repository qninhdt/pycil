import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ThemeToggle } from "@/components/theme/theme-toggle"

/**
 * The theme preference.
 *
 * The control is the same one in the header rather than a second implementation. A
 * settings-only copy would be a second writer to the same stored preference, and the
 * two would disagree the moment either changed.
 *
 * Stored in the browser, not on the account: the API has no user preferences table, so
 * the card says so instead of implying the choice follows the learner to another device.
 */
export function AppearanceCard() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Appearance</CardTitle>
        <CardDescription>
          Light, dark, or whatever this device prefers. Saved in this browser, so each
          device keeps its own setting.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ThemeToggle />
      </CardContent>
    </Card>
  )
}
