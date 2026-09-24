"use client"

/**
 * The learner's monthly allowance, in Credits.
 *
 * Credits rather than currency, and never a "cost per message": a turn is billed
 * from the tokens the provider actually reported, so any per-message figure would
 * be a number this UI invented. `available` is the balance clamped at zero, which
 * is what keeps a slightly overspent account from rendering a negative allowance.
 *
 * The value is a snapshot, not a live meter. It refreshes when the assistant
 * surface opens and after a turn finishes, which is often enough for a number the
 * learner checks occasionally and never the thing a turn depends on.
 */

import { useEffect, useState } from "react"

import { readCredit } from "@/lib/actions/account"
import type { AccountCredit } from "@/lib/api/types"

/** One decimal is enough to show a fractional Credit without implying precision. */
function formatCredits(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)
}

function formatRenewal(periodEnd: string): string {
  const date = new Date(periodEnd)
  if (Number.isNaN(date.getTime())) return ""
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date)
}

export function CreditMeter() {
  const [credit, setCredit] = useState<AccountCredit | null>(null)

  useEffect(() => {
    let active = true
    void readCredit().then((result) => {
      if (active && result.success) setCredit(result.data)
    })
    return () => {
      active = false
    }
  }, [])

  // Absent rather than zeroed while unknown: a learner should not see "0 Credits"
  // because a read was slow.
  if (!credit) return null

  const renewal = formatRenewal(credit.periodEnd)
  const exhausted = credit.available <= 0

  return (
    <p
      className="text-xs text-muted-foreground"
      aria-label={`${formatCredits(credit.available)} of ${formatCredits(credit.periodGrant)} Credits remaining`}
    >
      <span className={exhausted ? "font-medium text-destructive" : "font-medium text-foreground"}>
        {formatCredits(credit.available)}
      </span>
      {" / "}
      {formatCredits(credit.periodGrant)} Credits
      {renewal ? ` · renews ${renewal}` : ""}
    </p>
  )
}
