import type { Fetcher } from "../request"
import type { AccountCredit, AccountExport, Capabilities, Viewer } from "../types"

/**
 * The account endpoints Pycil still serves.
 *
 * Sign-in, sign-out and session refresh are Clerk's: there is no Pycil login URL
 * to fetch and no Pycil logout route to call, so neither is listed here. Adding
 * one back would be a second session issuer.
 */
export function authResource(fetch: Fetcher) {
  return {
    getViewer: () => fetch<Viewer>("/v1/me"),
    getCapabilities: () => fetch<Capabilities>("/v1/capabilities"),
    /** The monthly allowance, in Credits rather than currency. */
    getCredit: () => fetch<AccountCredit>("/v1/me/credit"),
    exportAccount: () => fetch<AccountExport>("/v1/me/export"),
    deleteAccount: () =>
      fetch<void>("/v1/me", {
        method: "DELETE",
        body: JSON.stringify({ confirmation: "DELETE" }),
      }),
  }
}
