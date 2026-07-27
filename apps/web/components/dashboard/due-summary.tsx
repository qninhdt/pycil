import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card"
import { masteryStageAttr, masteryStageName } from "@/lib/design/mastery"

/**
 * The two figures a learner opens the app for: how much is due, and how far
 * along they are overall.
 *
 * Both are set as large type rather than in a chart. A number this important
 * should be readable in the first glance, and a gauge for a single percentage is
 * decoration with a legend.
 */
export function DueSummary({
  dueTodayCount,
  masteryPercentage,
  totalLearnedWords,
}: {
  dueTodayCount: number
  masteryPercentage: number
  totalLearnedWords: number
}) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Card>
        <CardContent className="flex flex-col gap-1">
          <CardDescription>Due today</CardDescription>
          <CardTitle className="text-4xl tabular-nums">{dueTodayCount}</CardTitle>
          <p className="text-sm text-muted-foreground">
            {dueTodayCount === 0
              ? "Nothing is due. Anything you study now is ahead of schedule."
              : `${dueTodayCount === 1 ? "word" : "words"} scheduled for review`}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-1">
          <CardDescription>Mastery</CardDescription>
          <CardTitle
            className="stage-text text-4xl tabular-nums"
            data-stage={masteryStageAttr(masteryPercentage)}
          >
            {masteryPercentage}%
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            {masteryStageName(masteryPercentage)} across {totalLearnedWords}{" "}
            {totalLearnedWords === 1 ? "word" : "words"}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
