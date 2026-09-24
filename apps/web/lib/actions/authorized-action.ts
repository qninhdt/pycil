import { createApiClient, type ApiClient } from "@/lib/api/client"
import { handleAction, type ActionResult } from "@/lib/api/handle-api-error"

/** Browser command seam: cookies authenticate the direct same-origin request. */
export async function withClient<T>(
  run: (client: ApiClient) => Promise<T>,
): Promise<ActionResult<T>> {
  return handleAction(() => run(createApiClient()))
}
