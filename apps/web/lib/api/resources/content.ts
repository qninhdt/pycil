import type { Fetcher } from "../request"
import { queryString } from "../request"
import type { GenerationCreated, SenseDetail, WordSearchResult } from "../types"

/** Dictionary reads and the asynchronous word generation that fills gaps. */
export function contentResource(fetch: Fetcher) {
  return {
    /**
     * Ranked search results.
     *
     * The ranking is the API's, so a consumer must not re-sort or re-filter the
     * list — the command palette runs with client filtering disabled for exactly
     * this reason.
     */
    searchWords: (query: string) =>
      fetch<WordSearchResult[]>(`/v1/words/search${queryString({ q: query })}`),

    getSense: (senseId: number) => fetch<SenseDetail>(`/v1/senses/${senseId}`),

    /**
     * Requests a word the dictionary does not have yet.
     *
     * Returns a task id, not content: generation runs in the background and
     * settles through a realtime snapshot.
     */
    generateWord: (query: string) =>
      fetch<GenerationCreated>("/v1/word-generations", {
        method: "POST",
        body: JSON.stringify({ query }),
      }),
  }
}
