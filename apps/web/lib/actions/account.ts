import type { ActionResult } from "@/lib/api/handle-api-error"
import type { AccountCredit, AccountExport } from "@/lib/api/types"

import { withClient } from "./authorized-action"

/** The monthly allowance, in Credits. Read-only; the debit path owns the write. */
export function readCredit(): Promise<ActionResult<AccountCredit>> {
  return withClient((client) => client.auth.getCredit())
}

export function exportAccount(): Promise<ActionResult<AccountExport>> {
  return withClient((client) => client.auth.exportAccount())
}

export function deleteAccount(): Promise<ActionResult<void>> {
  return withClient((client) => client.auth.deleteAccount())
}
