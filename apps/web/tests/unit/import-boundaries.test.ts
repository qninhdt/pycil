import { ESLint } from "eslint"
import { fileURLToPath } from "node:url"
import path from "node:path"
import { describe, expect, it } from "vitest"

/**
 * Proves the import-boundary rules in `eslint.config.mjs` fire.
 *
 * A lint rule nobody ever sees fail is decoration: it gets disabled during a
 * rushed change and the boundary quietly dissolves. So this suite lints
 * deliberate violations through the real config and fails if they come back
 * clean — the rules are watched-failing by construction.
 */

const webRoot = fileURLToPath(new URL("../..", import.meta.url))

/** Lints an in-memory snippet as if it lived at `filePath`. */
async function restrictedImportCount(
  filePath: string,
  code: string
): Promise<number> {
  const eslint = new ESLint({ cwd: webRoot })
  const [result] = await eslint.lintText(code, { filePath })
  return result.messages.filter(
    (message) => message.ruleId === "no-restricted-imports"
  ).length
}

describe("import boundaries", () => {
  it("flags a component importing lib/api internals", async () => {
    const violations = await restrictedImportCount(
      path.join(webRoot, "components/library/boundary-probe.ts"),
      'import { createFetcher } from "@/lib/api/request"\n'
    )
    expect(violations).toBeGreaterThan(0)
  })

  it("flags the same violation through a relative specifier", async () => {
    const violations = await restrictedImportCount(
      path.join(webRoot, "components/library/boundary-probe.ts"),
      'import { createFetcher } from "../../lib/api/request"\n'
    )
    expect(violations).toBeGreaterThan(0)
  })

  it("keeps the public lib/api surfaces open to components", async () => {
    const violations = await restrictedImportCount(
      path.join(webRoot, "components/library/boundary-probe.ts"),
      [
        'import type { NodeRead } from "@/lib/api/types"',
        'import { classifyErrorCode } from "@/lib/api/error-taxonomy"',
        "",
      ].join("\n")
    )
    expect(violations).toBe(0)
  })

  it("flags a feature importing another feature's files", async () => {
    const violations = await restrictedImportCount(
      path.join(webRoot, "components/library/boundary-probe.ts"),
      'import { QuestionBody } from "@/components/study/question-body"\n'
    )
    expect(violations).toBeGreaterThan(0)
  })

  it("leaves same-feature and shared-layer imports alone", async () => {
    const violations = await restrictedImportCount(
      path.join(webRoot, "components/library/boundary-probe.ts"),
      [
        'import { nodeTypeLabel } from "./node-icon"',
        'import { Button } from "@/components/ui/button"',
        'import { Headword } from "@/components/vocabulary/headword"',
        "",
      ].join("\n")
    )
    expect(violations).toBe(0)
  })
})
