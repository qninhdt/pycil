import { readdir, readFile } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { expect, test } from "@playwright/test"

// The package is ESM, so `__dirname` does not exist here. It resolved to a
// ReferenceError at run time rather than at import, which is why the spec failed as a
// runtime fault inside the test body instead of never collecting.
const here = path.dirname(fileURLToPath(import.meta.url))

async function filesUnder(dir: string): Promise<string[]> {
  const found: string[] = []
  const walk = async (current: string): Promise<void> => {
    let entries
    try {
      entries = await readdir(current, { withFileTypes: true })
    } catch {
      return
    }
    for (const entry of entries) {
      const full = path.join(current, entry.name)
      if (entry.isDirectory()) await walk(full)
      else found.push(full)
    }
  }
  await walk(dir)
  return found
}

test("the browser bundle contains no server credential custody", async () => {
  const root = path.resolve(here, "../../../../..")
  const files = await filesUnder(path.join(root, "apps/web/.next/static"))
  test.skip(files.length === 0, "build the web app before running bundle hygiene")

  const forbidden = ["SESSION_PASSWORD", "PYCIL_API_URL", "refreshToken", "accessToken"]
  const leaks: string[] = []
  for (const file of files) {
    if (!/\.(js|mjs|cjs|css|json|txt|map)$/.test(file)) continue
    const content = await readFile(file, "utf8")
    for (const value of forbidden) if (content.includes(value)) leaks.push(path.relative(root, file))
  }
  expect(leaks).toEqual([])
})
