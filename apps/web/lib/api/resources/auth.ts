import type { Fetcher } from "../request"
import type { AccountExport, Capabilities, RealtimeToken, Viewer } from "../types"

/** Identity, capabilities, realtime tokens, and the account lifecycle. */
export function authResource(fetch: Fetcher) {
  return {
    getViewer: () => fetch<Viewer>("/v1/me"),

    getCapabilities: () => fetch<Capabilities>("/v1/capabilities"),

    /**
     * Mints a short-lived Centrifugo token. The provider re-mints on refresh
     * rather than holding the first value, because this expires well inside a
     * long session.
     */
    getRealtimeToken: () => fetch<RealtimeToken>("/v1/realtime/token"),

    exportAccount: () => fetch<AccountExport>("/v1/me/export"),

    /**
     * Deletes the account irreversibly.
     *
     * Both body fields are snake_case on purpose: this is a request model, and
     * the API does not alias its inputs. The literal confirmation is the API's
     * own guard — a wrong value is rejected server-side.
     */
    deleteAccount: (refreshToken: string) =>
      fetch<void>("/v1/me", {
        method: "DELETE",
        body: JSON.stringify({ confirmation: "DELETE", refresh_token: refreshToken }),
      }),
  }
}
