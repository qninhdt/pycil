import path from "node:path"
import { fileURLToPath } from "node:url"

import type { NextConfig } from "next"

const here = path.dirname(fileURLToPath(import.meta.url))

const nextConfig: NextConfig = {
  /**
   * Traces the server build down to the files it actually imports, so the
   * container ships a runnable app instead of the whole pnpm store. A pnpm
   * workspace makes this close to mandatory: `node_modules` is a symlink farm
   * into `.pnpm`, and copying it into an image either breaks the links or drags
   * in every dev dependency.
   */
  output: "standalone",
  /**
   * The workspace root, not this directory, because tracing has to follow those
   * symlinks out to `.pnpm`. Resolved from this file rather than `process.cwd()`
   * so the build produces the same output whether it is started here or from the
   * repository root.
   */
  outputFileTracingRoot: path.join(here, "../.."),
}

export default nextConfig
