import { describe, expect, it } from "vitest"

import {
  ERROR_TAXONOMY,
  classifyErrorCode,
  isRetryable,
} from "@/lib/api/error-taxonomy"
import { API_ERROR_STATUS } from "@/lib/api/error-codes.generated"

/**
 * The wire-code → behaviour map.
 *
 * The type system already guarantees an entry exists for every generated code
 * (the map is `Record<ApiErrorCode, …>`, so a missing one fails the typecheck).
 * These tests guard what the compiler cannot: that a code this build has never
 * heard of degrades to a generic message instead of throwing, that the category
 * helpers agree with the table, and that no learner-facing message leaks the raw
 * code or an internal component name.
 */

describe("classifyErrorCode", () => {
  it("classifies a known code from the table", () => {
    const entry = classifyErrorCode("session_scope_changed")
    expect(entry.category).toBe("session_invalidated")
    expect(entry.message).toBe(ERROR_TAXONOMY.session_scope_changed.message)
  })

  it("degrades an unknown wire code to the generic fallback rather than throwing", () => {
    // A newer API can send a code this build predates. It must not throw, and it
    // must not surface the raw code to the learner.
    const entry = classifyErrorCode("a_code_from_the_future")
    expect(entry.category).toBe("unexpected")
    expect(entry.message).toBe("Something went wrong. Try again.")
  })

  it("has an entry for every generated wire code", () => {
    // Belt-and-braces around the compile-time guarantee: every code the API can
    // emit resolves to a real entry, so classification is never the fallback for
    // a code we do ship.
    for (const code of Object.keys(API_ERROR_STATUS)) {
      expect(ERROR_TAXONOMY[code as keyof typeof ERROR_TAXONOMY]).toBeDefined()
    }
  })
})

describe("category helpers", () => {
  it("isRetryable is true only for the retryable category", () => {
    expect(isRetryable("centrifugo_unavailable")).toBe(true)
    expect(isRetryable("service_unavailable")).toBe(true)
    expect(isRetryable("session_not_found")).toBe(false)
    expect(isRetryable("a_code_from_the_future")).toBe(false)
  })

  it("marks as session_invalidated exactly the codes that end a session", () => {
    // Asserted through the category rather than through a helper, because the
    // category is what the study reducer branches on. A code moved into or out of
    // `session_invalidated` changes whether the learner is told their session is
    // over, which is the single most consequential classification in the table.
    expect(classifyErrorCode("session_not_found").category).toBe("session_invalidated")
    expect(classifyErrorCode("session_scope_changed").category).toBe("session_invalidated")
    expect(classifyErrorCode("question_not_available").category).toBe("session_invalidated")
    // A conflict is not a session end: question_not_assessable is answerable-elsewhere,
    // not session-over.
    expect(classifyErrorCode("question_not_assessable").category).toBe("conflict")
    expect(classifyErrorCode("word_generation_quota_exceeded").category).not.toBe(
      "session_invalidated",
    )
  })
})

/**
 * The four codes that used to arrive as one generic conflict.
 *
 * Listed here rather than exported from the module under test: nothing in the app
 * reads them as a set, and an export existing only so a test can import it is an
 * export that outlives whatever made it worth having.
 */
const SESSION_INTERRUPTION_CODES = [
  "session_scope_changed",
  "question_not_assessable",
  "question_not_issued_for_session",
  "question_not_available",
] as const

describe("session interruption codes", () => {
  it("every interruption code has a taxonomy entry", () => {
    for (const code of SESSION_INTERRUPTION_CODES) {
      expect(ERROR_TAXONOMY[code]).toBeDefined()
    }
  })

  it("splits the four codes that used to arrive as one generic conflict", () => {
    // The reason the API-side error work mattered: these four must classify
    // distinctly so the study screen can branch. Three end the session; the
    // fourth is a not-your-question conflict the learner recovers from.
    expect(classifyErrorCode("session_scope_changed").category).toBe("session_invalidated")
    expect(classifyErrorCode("question_not_available").category).toBe("session_invalidated")
    expect(classifyErrorCode("question_not_issued_for_session").category).toBe(
      "session_invalidated",
    )
    expect(classifyErrorCode("question_not_assessable").category).toBe("conflict")
  })
})

describe("messages", () => {
  it("never echo the raw code and never name an internal component", () => {
    for (const [code, entry] of Object.entries(ERROR_TAXONOMY)) {
      // The jargon a learner must never see is the snake_case wire identifier.
      // A single English word that happens to be a code — "conflict" reads
      // naturally in "That conflicts with the current state" — is not a leak, so
      // only the underscore-bearing identifiers are asserted absent.
      if (code.includes("_")) {
        expect(entry.message).not.toContain(code)
      }
      expect(entry.message.toLowerCase()).not.toContain("lexi")
      expect(entry.message.toLowerCase()).not.toContain("centrifugo")
    }
  })
})
