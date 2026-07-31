#!/usr/bin/env node
/**
 * Generates `app/tokens.generated.css` from the root `DESIGN.md`.
 *
 * The exporter emits a flat `@theme` block using Tailwind's own namespaces
 * (`--color-*`, `--font-*`, `--radius-*`, ...). Several of those names are
 * already owned by the base-nova primitive layer's `@theme inline`, where they
 * are indirections such as `--color-border: var(--border)`. Two `@theme` blocks
 * defining one name resolve last-wins, so shipping the exporter's output as-is
 * would silently destroy either the literal palette or the semantic layer.
 *
 * So every exported name is moved into a `--pycil-*` namespace and emitted into
 * `:root` instead of `@theme`. Two consequences, both wanted:
 *   - the raw palette can never collide with a Tailwind theme namespace;
 *   - raw tokens generate no utilities, so `bg-pycil-ink` does not exist and
 *     call sites are forced through the semantic layer in `globals.css`.
 *
 * Both this script and its output are committed, so `next build` never needs
 * the exporter or a network fetch.
 */
import { execFileSync } from "node:child_process"
import { writeFileSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..")
const designSpec = resolve(webRoot, "../../DESIGN.md")
const outFile = resolve(webRoot, "app/tokens.generated.css")

const exported = execFileSync(
  "design.md",
  ["export", designSpec, "--format", "css-tailwind"],
  { encoding: "utf8", cwd: webRoot },
)

/**
 * `--color-ink` becomes `--pycil-ink` so colour reads stay short, while every
 * other namespace keeps its segment (`--radius-sm` to `--pycil-radius-sm`) so
 * the token's kind is still legible at the use site.
 */
function namespaceToken(name) {
  return name.startsWith("--color-")
    ? `--pycil-${name.slice("--color-".length)}`
    : `--pycil-${name.slice("--".length)}`
}

const declarations = []
for (const line of exported.split("\n")) {
  const match = line.match(/^\s*(--[\w-]+)\s*:\s*(.+?);\s*$/)
  if (match) declarations.push([namespaceToken(match[1]), match[2]])
}

if (declarations.length === 0) {
  throw new Error("design.md export produced no token declarations")
}

const duplicates = declarations
  .map(([name]) => name)
  .filter((name, index, all) => all.indexOf(name) !== index)
if (duplicates.length > 0) {
  throw new Error(`namespacing collapsed distinct tokens: ${duplicates.join(", ")}`)
}

/**
 * Relative luminance per WCAG 2.1, used for the two dark-mode rules below.
 * Contrast ratio alone cannot express either of them: a pale wash on a dark
 * ground scores about 10:1 against its own foreground and still reads as a
 * glowing slab, and an inverted ramp keeps every pair perfectly legible.
 */
function relativeLuminance(hex) {
  const channels = [1, 3, 5].map((offset) => {
    const srgb = parseInt(hex.slice(offset, offset + 2), 16) / 255
    return srgb <= 0.03928 ? srgb / 12.92 : ((srgb + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]
}

const byName = new Map(declarations)

function luminanceOf(token) {
  const value = byName.get(token)
  if (!/^#[0-9a-f]{6}$/i.test(value ?? "")) {
    throw new Error(`${token} is missing or is not a six-digit hex: ${value}`)
  }
  return relativeLuminance(value)
}

/**
 * A wash is a tag or banner background. In dark mode it must sit *behind* text
 * on a dark page, so it has to be darker than the surface it lands on.
 */
const darkSurface = luminanceOf("--pycil-dark-surface")
const glowing = ["primary", "success", "danger", "warn", "info"].filter(
  (name) => luminanceOf(`--pycil-dark-${name}-wash`) >= darkSurface,
)
if (glowing.length > 0) {
  throw new Error(
    `dark washes must be darker than dark-surface, these are lighter: ${glowing.join(", ")}`,
  )
}

/**
 * The mastery ramp is one ordered dimension: more colour means more learned.
 * On a dark ground that reading only survives if the ramp ascends in
 * luminance, which is the opposite direction from the light ramp.
 */
const darkRamp = [1, 2, 3, 4, 5].map((stage) => luminanceOf(`--pycil-dark-stage-${stage}`))
const notAscending = darkRamp.findIndex(
  (luminance, index) => index > 0 && luminance <= darkRamp[index - 1],
)
if (notAscending > 0) {
  throw new Error(
    `the dark mastery ramp must ascend so stage 5 is most visible; ` +
      `stage ${notAscending + 1} is not brighter than stage ${notAscending}`,
  )
}

/**
 * The ink track carries the same five bands as *text*, and text has a contrast
 * floor the fill ramp does not.
 *
 * The fill ramp is tuned for pips, bars and chips, where a stage-1 chip at
 * 1.7:1 against white is the intended reading: barely there, because nothing is
 * learned yet. Applied to a numeral it is simply unreadable, and axe says so.
 * So a second track exists for text, asserted here rather than eyeballed:
 * every stage clears 4.5:1 against the lightest ground it lands on, and the
 * track still moves in the ramp's direction so the two never contradict each
 * other about which end means "more learned".
 */
function contrastRatio(a, b) {
  const [lighter, darker] = a > b ? [a, b] : [b, a]
  return (lighter + 0.05) / (darker + 0.05)
}

const STAGES = [1, 2, 3, 4, 5]
/** WCAG 2.1 AA for body-sized text. The numerals are larger, but not all of it is. */
const TEXT_CONTRAST_FLOOR = 4.5

for (const [track, ground] of [
  // The ground each track actually lands on. Light text sits on white cards, so
  // white is its worst case; dark text sits on the sunken surface, which is the
  // darkest ground and therefore the dark track's worst case is the surface it
  // is closest to in tone.
  ["stage-ink", "--pycil-surface"],
  ["dark-stage-ink", "--pycil-dark-surface"],
]) {
  const groundLuminance = luminanceOf(ground)
  for (const stage of STAGES) {
    const token = `--pycil-${track}-${stage}`
    const ratio = contrastRatio(luminanceOf(token), groundLuminance)
    if (ratio < TEXT_CONTRAST_FLOOR) {
      throw new Error(
        `${token} is text colour and scores ${ratio.toFixed(2)}:1 against ` +
          `${ground}; AA needs ${TEXT_CONTRAST_FLOOR}:1`,
      )
    }
  }
}

/**
 * And the ink track keeps the ramp's direction: darker with mastery in light
 * mode, brighter in dark mode. Without this a legible palette could still
 * reverse the meaning the fill ramp establishes.
 */
for (const [track, direction] of [
  ["stage-ink", "descend"],
  ["dark-stage-ink", "ascend"],
]) {
  const luminances = STAGES.map((stage) => luminanceOf(`--pycil-${track}-${stage}`))
  const broken = luminances.findIndex((luminance, index) => {
    if (index === 0) return false
    return direction === "ascend"
      ? luminance <= luminances[index - 1]
      : luminance >= luminances[index - 1]
  })
  if (broken > 0) {
    throw new Error(
      `the ${track} ink track must ${direction} in luminance so stage 5 reads as ` +
        `the most learned; stage ${broken + 1} breaks it`,
    )
  }
}

const body = declarations.map(([name, value]) => `  ${name}: ${value};`).join("\n")
const output = `/* Generated by scripts/build-design-tokens.mjs from /DESIGN.md. Do not edit.
   Raw palette only. The semantic mapping lives in app/globals.css. */
:root {
${body}
}
`

writeFileSync(outFile, output)
console.log(`wrote ${declarations.length} tokens to app/tokens.generated.css`)
