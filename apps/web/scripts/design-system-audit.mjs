#!/usr/bin/env node
/**
 * The ten mechanical design-system greps, as a gate rather than a memo.
 *
 * DESIGN.md encodes rules a typecheck cannot: serif is reserved for lexical
 * content, spacing goes through the flex/grid `gap` scale rather than
 * `space-*`, elevation is a hairline ring rather than a drop shadow, and colour
 * flows through the semantic layer rather than a raw hex or a `dark:` override
 * at the call site. Each rule below is one grep, and a hit in feature code fails
 * the build. The `components/ui/**` primitive registry (phase 6) is exempt,
 * because that layer is where the tokens are wired to Tailwind in the first
 * place; the rules exist to keep the *rest* of the app off the raw values.
 *
 * Run: `node scripts/design-system-audit.mjs` (wired as `pnpm --filter web audit:design`).
 * Exit code is non-zero on any violation, so CI can gate on it.
 *
 * **What this does not catch**, stated because a green gate reads as "the design
 * system holds" and it means something narrower than that:
 *
 * - **Contrast.** Nothing here computes a ratio, so a token pair that fails WCAG AA
 *   passes every rule below. The a11y spec's axe run is what covers that, on the
 *   routes it visits.
 * - **Anything outside `app/` and `components/`.** A raw hex in `lib/`, in a chart
 *   config, or in `globals.css` is unseen.
 * - **Classes composed through `cn()` or a variable.** The greps read source text,
 *   so `cn("p-4", condition && "shadow-lg")` is caught but
 *   `` cn(`shadow-${size}`) `` is not.
 * - **Semantic token misuse.** Using `bg-destructive` for a neutral surface goes
 *   through the semantic layer and is therefore correct by these rules and wrong by
 *   the design system.
 * - **Dark-mode token parity.** A token defined for light and not dark passes: the
 *   `dark:` rule forbids call-site overrides, it does not check the palette is
 *   complete.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { dirname, extname, join, relative, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..")

/**
 * The primitive registry is the one place raw tokens are legitimately wired, so
 * it is exempt from the call-site rules. Everything else under `app/` and
 * `components/` is feature code and must go through the semantic layer.
 */
const SCAN_DIRS = ["app", "components"]
const UI_REGISTRY = join("components", "ui")

/** Collects every `.ts`/`.tsx` file under the scanned directories. */
function collectFiles() {
  const out = []
  for (const dir of SCAN_DIRS) walk(resolve(webRoot, dir), out)
  return out
}

function walk(absDir, out) {
  let entries
  try {
    entries = readdirSync(absDir)
  } catch {
    return
  }
  for (const entry of entries) {
    const abs = join(absDir, entry)
    if (statSync(abs).isDirectory()) {
      walk(abs, out)
    } else if ([".ts", ".tsx"].includes(extname(abs))) {
      out.push(abs)
    }
  }
}

/**
 * A file's source with its comments blanked but its strings kept, split into
 * lines whose numbering matches the original.
 *
 * The rules are about what the source *does*, not what a comment says about it.
 * The word "shadow" in a JSDoc sentence and an em dash in a `{/* … *\/}` note are
 * not violations; a `shadow-lg` in a real `className` is. So comments — line and
 * block, tracked across lines — are blanked, while string and JSX-text content is
 * preserved: a Tailwind class lives inside a `className="…"` string and a raw hex
 * lives inside `color: "#…"`, so blanking strings (the previous bug) made every
 * class and colour rule match nothing and pass vacuously.
 *
 * Newlines are preserved through blanked comments so a hit still reports the line
 * it is really on, which is what lets the em-dash rule see a multi-line JSDoc block
 * as comment rather than code.
 */
function stripComments(source) {
  let out = ""
  let state = "code" // code | line | block | sq | dq | tpl
  for (let i = 0; i < source.length; i++) {
    const ch = source[i]
    const next = source[i + 1]
    if (state === "code") {
      if (ch === "/" && next === "/") {
        state = "line"
        out += "  "
        i++
      } else if (ch === "/" && next === "*") {
        state = "block"
        out += "  "
        i++
      } else if (ch === "'") {
        state = "sq"
        out += ch
      } else if (ch === '"') {
        state = "dq"
        out += ch
      } else if (ch === "`") {
        state = "tpl"
        out += ch
      } else {
        out += ch
      }
      continue
    }
    if (state === "line") {
      if (ch === "\n") {
        state = "code"
        out += "\n"
      } else {
        out += " "
      }
      continue
    }
    if (state === "block") {
      if (ch === "*" && next === "/") {
        state = "code"
        out += "  "
        i++
      } else {
        out += ch === "\n" ? "\n" : " "
      }
      continue
    }
    // A string literal: copied verbatim, honouring escapes, until its own quote.
    const quote = state === "sq" ? "'" : state === "dq" ? '"' : "`"
    if (ch === "\\") {
      out += ch + (next ?? "")
      i++
    } else if (ch === quote) {
      state = "code"
      out += ch
    } else {
      out += ch
    }
  }
  return out.split("\n")
}

/**
 * @typedef {object} Rule
 * @property {string} name        one-line description shown in the report
 * @property {RegExp} pattern     matched against each comment-stripped line
 * @property {(file: string) => boolean} [exempt]  files this rule does not apply to
 */

const inRegistry = (file) => relative(webRoot, file).startsWith(UI_REGISTRY)

/** @type {Rule[]} */
const RULES = [
  {
    // Em dashes are an editorial tell, banned in the prose a learner reads.
    // Comments legitimately use them and are blanked before matching, so a hit
    // is an em dash in real code — a string literal or JSX text that renders.
    name: "no em dash in rendered text",
    pattern: /—/,
  },
  {
    name: "no space-y-* / space-x-* (use gap on a flex/grid parent)",
    pattern: /\bspace-[xy]-/,
    exempt: inRegistry,
  },
  {
    name: "no drop shadow (elevation is a hairline ring)",
    pattern: /\bshadow-(md|lg|xl|2xl)\b/,
    exempt: inRegistry,
  },
  {
    name: "no h-screen (use min-h-[100dvh] for mobile Safari)",
    pattern: /\bh-screen\b/,
    exempt: inRegistry,
  },
  {
    // The two exempt files cannot use the token layer by construction: the global
    // error boundary replaces the root layout, so it renders before any stylesheet
    // or CSS variable exists, and the `themeColor` viewport meta drives browser
    // chrome, which a CSS variable cannot reach. Both are documented at the source.
    name: "no raw hex colour (go through the semantic token layer)",
    pattern: /#[0-9a-fA-F]{3,8}\b/,
    exempt: (file) => {
      const rel = relative(webRoot, file)
      return (
        inRegistry(file) ||
        rel === "app/global-error.tsx" ||
        rel === "app/layout.tsx"
      )
    },
  },
  {
    name: "no dark: colour override at a call site",
    pattern: /\bdark:(bg|text|border|ring|from|to|via)-/,
    exempt: inRegistry,
  },
  {
    name: "no lucide-react import (icons come from lib/icons)",
    pattern: /from\s+["']lucide-react["']/,
  },
  {
    name: "no w-N h-N pair where size-N applies",
    pattern: /\bw-(\d+(?:\.\d+)?)\s+h-\1\b|\bh-(\d+(?:\.\d+)?)\s+w-\2\b/,
    exempt: inRegistry,
  },
]

/**
 * The serif rule is structural, not a grep for a class: `font-serif` is allowed,
 * but only on lexical content. The allow-list is the set of files that render a
 * word, a definition, a headword, or the brand wordmark. A new serif anywhere
 * else is the violation — a panel heading or a button creeping into the reading
 * face.
 */
const SERIF_ALLOWED = new Set([
  "app/(auth)/login/page.tsx", // brand wordmark
  "components/shell/nav-rail.tsx", // brand wordmark
  "components/shell/app-header.tsx", // brand wordmark
  "components/vocabulary/headword.tsx",
  "components/vocabulary/definition-block.tsx",
  "components/vocabulary/example-list.tsx", // example sentences
  "components/vocabulary/relation-list.tsx", // related headwords
  "components/library/deck-item-row.tsx", // the word on a deck row
  "components/dashboard/weakest-preview.tsx", // weakest words
  "components/progress/weakest-word-list.tsx", // weakest words
  "components/activity/activity-task-row.tsx", // the word a task is about
  "components/assistant/approval-request-card.tsx", // the node/deck name being acted on
  "components/command/palette-create-group.tsx", // the word being created
  "components/command/palette-word-results.tsx", // searched headwords
  "components/study/reveal-display.tsx", // the disclosed answer, dictionary content
])

/** A file's comment-stripped lines, read and parsed once. */
function strippedLinesOf(file) {
  return stripComments(readFileSync(file, "utf8"))
}

function auditSerif(files) {
  const violations = []
  for (const file of files) {
    const rel = relative(webRoot, file)
    if (SERIF_ALLOWED.has(rel)) continue
    strippedLinesOf(file).forEach((line, i) => {
      if (/\bfont-serif\b/.test(line)) {
        violations.push(`${rel}:${i + 1}: ${line.trim()}`)
      }
    })
  }
  return violations
}

/**
 * Every `rounded-*` radius must resolve to a defined `--radius-*` token. An
 * undefined token silently falls back to a Tailwind default, so the corner a
 * component renders is not the corner the design system specifies. This reads
 * the token names straight from the generated theme so the check cannot drift
 * from the source of truth.
 */
function auditRadius(files) {
  const css = readFileSync(resolve(webRoot, "app/globals.css"), "utf8")
  const defined = new Set(
    [...css.matchAll(/--radius-([\w]+)\s*:/g)].map((m) => m[1]),
  )
  // Tailwind's own always-defined radii, present without a custom token.
  const builtin = new Set(["none", "full"])
  const violations = []
  for (const file of files) {
    const rel = relative(webRoot, file)
    strippedLinesOf(file).forEach((line, i) => {
      for (const m of line.matchAll(/\brounded-(?:[tblrse]{1,2}-)?([\w]+)\b/g)) {
        const size = m[1]
        if (builtin.has(size) || defined.has(size)) continue
        // A bare `rounded` (no size) and directional-only classes map to the
        // default radius token, which is defined; only a named size can dangle.
        violations.push(`${rel}:${i + 1}: rounded-${size} has no --radius-${size} token`)
      }
    })
  }
  return violations
}

function auditRule(rule, files) {
  const violations = []
  for (const file of files) {
    if (rule.exempt?.(file)) continue
    const rel = relative(webRoot, file)
    strippedLinesOf(file).forEach((line, i) => {
      if (rule.pattern.test(line)) {
        violations.push(`${rel}:${i + 1}: ${line.trim()}`)
      }
    })
  }
  return violations
}

function main() {
  const files = collectFiles()
  const results = []

  for (const rule of RULES) {
    results.push({ name: rule.name, violations: auditRule(rule, files) })
  }
  results.push({ name: "serif reserved for lexical content", violations: auditSerif(files) })
  results.push({ name: "every rounded-* radius token is defined", violations: auditRadius(files) })

  let failed = 0
  for (const { name, violations } of results) {
    if (violations.length === 0) {
      process.stdout.write(`  ok    ${name}\n`)
      continue
    }
    failed++
    process.stdout.write(`  FAIL  ${name} (${violations.length})\n`)
    for (const v of violations) process.stdout.write(`          ${v}\n`)
  }

  process.stdout.write(
    `\n${results.length - failed}/${results.length} checks clean across ${files.length} files\n`,
  )
  process.exit(failed === 0 ? 0 : 1)
}

main()
