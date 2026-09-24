import { createFetcher } from "./request"
import { analyticsResource } from "./resources/analytics"
import { assistantResource } from "./resources/assistant"
import { authResource } from "./resources/auth"
import { contentResource } from "./resources/content"
import { hierarchyResource } from "./resources/hierarchy"
import { learningResource } from "./resources/learning"
import { jobsResource } from "./resources/jobs"

/** Direct same-origin API client. Credentials stay in HttpOnly cookies. */
export function createApiClient() {
  const fetch = createFetcher()
  return {
    auth: authResource(fetch),
    hierarchy: hierarchyResource(fetch),
    content: contentResource(fetch),
    learning: learningResource(fetch),
    analytics: analyticsResource(fetch),
    assistant: assistantResource(fetch),
    jobs: jobsResource(fetch),
  }
}

export type ApiClient = ReturnType<typeof createApiClient>
