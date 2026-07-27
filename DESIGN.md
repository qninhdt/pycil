---
version: alpha
name: Pycil Reading Room
description: Warm-monochrome editorial product UI for an FSRS vocabulary trainer. Dictionary-grade typography, one accent, near-zero elevation, motion you notice only when it is missing.
colors:
  ink: "#191817"
  on-ink: "#FBFAF8"
  bone: "#FBFAF8"
  surface: "#FFFFFF"
  surface-sunken: "#F5F3EF"
  border: "#E7E4DF"
  border-strong: "#D6D2CA"
  foreground: "#1F1E1C"
  muted-foreground: "#6B6760"
  primary: "#2E4A6E"
  on-primary: "#FFFFFF"
  primary-wash: "#EAEFF6"
  on-primary-wash: "#274364"
  success-wash: "#EDF3EC"
  on-success-wash: "#2F5C33"
  danger-wash: "#FCEBEB"
  on-danger-wash: "#98302D"
  warn-wash: "#FBF3DB"
  on-warn-wash: "#7F5400"
  info-wash: "#E7F1FA"
  on-info-wash: "#1F5A85"
  stage-1: "#C9C5BE"
  stage-2: "#9AA7B8"
  stage-3: "#6E86A6"
  stage-4: "#47688F"
  stage-5: "#2E4A6E"
  dark-bone: "#131211"
  dark-surface: "#1A1917"
  dark-surface-sunken: "#100F0E"
  dark-border: "#2C2A26"
  dark-border-strong: "#3C3934"
  dark-foreground: "#EDEAE4"
  dark-muted-foreground: "#9A958C"
  dark-primary: "#93B2DA"
  dark-on-primary: "#101822"
  destructive: "#A3302C"
  on-destructive: "#FDF6F5"
  dark-ink: "#EDEAE4"
  dark-on-ink: "#131211"
  dark-primary-wash: "#0B1622"
  dark-on-primary-wash: "#A5C8EC"
  dark-success-wash: "#0C170F"
  dark-on-success-wash: "#A7D3AC"
  dark-danger-wash: "#1B0D0D"
  dark-on-danger-wash: "#F0A9A4"
  dark-warn-wash: "#191207"
  dark-on-warn-wash: "#E8C879"
  dark-info-wash: "#0B1520"
  dark-on-info-wash: "#9FC9E8"
  dark-destructive: "#E8938C"
  dark-on-destructive: "#1A0A09"
  dark-stage-1: "#3C3934"
  dark-stage-2: "#4E5A6B"
  dark-stage-3: "#64788F"
  dark-stage-4: "#7B96BC"
  dark-stage-5: "#93B2DA"
typography:
  headword:
    fontFamily: Newsreader
    fontSize: 2rem
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -0.02em
  gloss:
    fontFamily: Newsreader
    fontSize: 1.0625rem
    fontWeight: 400
    lineHeight: 1.65
  title:
    fontFamily: Geist
    fontSize: 1.375rem
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: -0.015em
  heading:
    fontFamily: Geist
    fontSize: 1.0625rem
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: -0.01em
  body:
    fontFamily: Geist
    fontSize: 0.9375rem
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: Geist
    fontSize: 0.8125rem
    fontWeight: 500
    lineHeight: 1.4
  label-caps:
    fontFamily: Geist
    fontSize: 0.6875rem
    fontWeight: 600
    lineHeight: 1
    letterSpacing: 0.09em
  meta-mono:
    fontFamily: Geist Mono
    fontSize: 0.75rem
    fontWeight: 400
    lineHeight: 1.4
  numeral:
    fontFamily: Geist Mono
    fontSize: 1.75rem
    fontWeight: 500
    lineHeight: 1
    letterSpacing: -0.01em
    fontFeature: tnum
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  pill: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-primary-hover:
    backgroundColor: "#2E2C29"
    textColor: "{colors.on-ink}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  button-accent:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 12px
    height: 40px
  surface-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 20px
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: 10px
    height: 40px
  tag-neutral:
    backgroundColor: "{colors.surface-sunken}"
    textColor: "{colors.muted-foreground}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.pill}"
    padding: 6px
  tag-correct:
    backgroundColor: "{colors.success-wash}"
    textColor: "{colors.on-success-wash}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.pill}"
    padding: 6px
  tag-incorrect:
    backgroundColor: "{colors.danger-wash}"
    textColor: "{colors.on-danger-wash}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.pill}"
    padding: 6px
  tag-pending:
    backgroundColor: "{colors.warn-wash}"
    textColor: "{colors.on-warn-wash}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.pill}"
    padding: 6px
  tag-realtime:
    backgroundColor: "{colors.info-wash}"
    textColor: "{colors.on-info-wash}"
    typography: "{typography.label-caps}"
    rounded: "{rounded.pill}"
    padding: 6px
  tag-cefr:
    backgroundColor: "{colors.primary-wash}"
    textColor: "{colors.on-primary-wash}"
    typography: "{typography.meta-mono}"
    rounded: "{rounded.sm}"
    padding: 4px
  kbd-key:
    backgroundColor: "{colors.surface-sunken}"
    textColor: "{colors.muted-foreground}"
    typography: "{typography.meta-mono}"
    rounded: "{rounded.sm}"
    padding: 4px
  nav-tab-active:
    backgroundColor: "{colors.primary-wash}"
    textColor: "{colors.on-primary-wash}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 8px
  nav-tab-idle:
    backgroundColor: "{colors.bone}"
    textColor: "{colors.muted-foreground}"
    typography: "{typography.label}"
    rounded: "{rounded.md}"
    padding: 8px
  question-stage:
    backgroundColor: "{colors.bone}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 24px
  choice-option:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: 16px
    height: 56px
  choice-option-selected:
    backgroundColor: "{colors.primary-wash}"
    textColor: "{colors.on-primary-wash}"
  break-panel:
    backgroundColor: "{colors.surface-sunken}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 32px
  stat-figure:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    typography: "{typography.numeral}"
    rounded: "{rounded.lg}"
    padding: 20px
  assistant-panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 16px
    width: 380px
---

## Overview

**Pycil Reading Room.** The product is a dictionary you practice against, so the
interface behaves like a well-set reference book with a working desk beside it,
not like a gamified flashcard app and not like an analytics console.

Three commitments drive every decision below.

1. **The word is the artifact.** Headwords and definitions are set in a
   text-face serif at reading size. Everything else in the UI is a small,
   quiet sans-serif that gets out of the way. This is the only justified serif
   in the system: the content genuinely is lexicography.
2. **Progressive disclosure over completeness.** The backend exposes far more
   per-sense data than any single screen should show. Level 1 (the three
   destinations) shows only what answers "what do I study now?". Level 2 (deck
   and folder views) shows management. Level 3 (sense detail) is where the full
   lexical record lives. Nothing is deleted from the product, but nothing is
   dumped on the first screen either.
3. **The learning model is surfaced honestly.** Rounds, breaks, mastery bands,
   and difficulty fallbacks are real mechanics in the backend. They are named
   and shown, not hidden behind a single percentage bar. When the system
   penalises a learner because it could not serve the requested difficulty, the
   UI says so.

**Scope note.** This is dense product UI, not a marketing site. Landing-page
grammar (hero sections, bento marketing grids, marquees, scroll hijacking,
eyebrow labels above every section) is out of scope and banned here. The
anti-slop rules that *do* apply are the ones about typography, palette
discipline, interaction states, motion restraint, and content honesty.

**Dials.** `DESIGN_VARIANCE 5` - structured asymmetry, no decorative chaos.
`MOTION_INTENSITY 3` - state transitions only. `VISUAL_DENSITY 4` - daily-app
spacing, not gallery spacing.

## Information Architecture

Three navigation destinations. Everything else is a contextual surface reached
from within them.

```
Today          /                    what to study now, due load, forecast
Library        /library             folder + deck tree, node management
                /library/[nodeId]   deck view or folder view (type-switched)
Progress       /progress            mastery distribution, CEFR mix, history
```

Contextual surfaces, none of which is a tab:

| Surface | Trigger | Mobile | Desktop |
| --- | --- | --- | --- |
| Command palette | `Cmd/Ctrl K`, search field in Library header | Full-screen sheet | Centered dialog |
| Assistant | Header action, absent when `capabilities.assistant` is false | Bottom drawer | Right collapsible sidebar, 380px |
| Activity | Header action, badge counts unsettled tasks | Bottom drawer | Popover |
| Study | Start action on Today or a deck | Full screen, chrome hidden | Full screen, chrome hidden |
| Sense detail | Any word row, anywhere | Full-screen route | Full-screen route |
| Settings | Avatar menu | Route | Route |

Routes:

```
/                                   Today
/library                            root of tree
/library/[nodeId]                   deck or folder
/w/[senseId]                        sense detail (level 3)
/study/[sessionId]                  focus mode
/progress                           global analytics
/settings                           profile, deck defaults, data, danger zone
/login                              sign-in
```

`/w/[senseId]` is a global route because senses are globally identified and are
reached from search, from weakest-word lists, and from deck rows. Access is
authorised server-side; a sense the learner cannot read is a 404.

**Why search is not a destination.** Every search in this product is performed
in order to add a word to a specific deck. A standalone search page severs that
context, which is precisely how the previous implementation ended up needing a
separate "add to deck" modal. The palette carries the target deck with it.

## Colors

Warm monochrome with exactly one accent. Colour is a semantic resource, never
decoration.

**Neutrals.** `bone (#FBFAF8)` is the canvas, `surface (#FFFFFF)` is anything
raised out of it, `surface-sunken (#F5F3EF)` is anything pressed into it (input
wells, break panels, keycaps). `ink (#191817)` is the primary action fill and
never appears as page background. Text is `foreground (#1F1E1C)`, never pure
black; secondary text is `muted-foreground (#6B6760)`, which clears 5:1 on bone.

**The single accent.** `primary (#2E4A6E)` is a deep desaturated archive blue.
It marks interaction and only interaction: focus rings, active navigation,
selected answer options, links, and the top of the mastery ramp. It is not
purple, not neon, not gradient-filled. Once chosen it is used identically on
every screen. `primary-wash (#EAEFF6)` is its tinted-background form.

**Semantic washes.** Four pale backgrounds, each paired with a pre-checked
foreground: `success` for a correct verdict, `danger` for incorrect, `warn` for
anything unsettled or degraded (pending LLM grade, served-below-requested
fallback), `info` for realtime and connection state. These appear only as tag
and banner backgrounds, never as section fills.

**The mastery ramp.** The backend defines exactly five mastery bands in
`learning/policy.py` (`0-10 / 11-30 / 31-55 / 56-80 / 81-100`). The ramp
`stage-1` through `stage-5` walks warm graphite to the accent, so "more colour"
literally means "more learned". Stage names, used verbatim in the UI:

| Band | Token | Name | What the sampler actually does |
| --- | --- | --- | --- |
| 0-10 | `stage-1` | Introduced | 90% level 1 |
| 11-30 | `stage-2` | Recognised | 65% level 1, 30% level 2 |
| 31-55 | `stage-3` | Recalled | 55% level 2, 23% level 3 |
| 56-80 | `stage-4` | Applied | 55% level 3, 15% level 4 |
| 81-100 | `stage-5` | Fluent | 50% level 3, 40% level 4 |

A rainbow scale is forbidden here. Five hues would imply five unrelated
categories; this is one ordered dimension.

**Dark mode.** Mandatory and equal-effort. Warm-neutral dark, not blue-grey:
canvas `#131211`, surface `#1A1917`, border `#2C2A26`, text `#EDEAE4`. The
accent lifts to `#93B2DA` so it stays visible without glowing. One theme per
page load; sections never invert mid-scroll.

Dark mode is not a remapping of the neutrals with the washes left alone. Every
wash, every wash foreground, the destructive pair, and all five ramp stages have
their own dark values, because reusing a light wash on a dark ground produces a
near-white block that *passes* a contrast check while looking broken. Two rules
govern the dark values and both are asserted mechanically rather than eyeballed:

1. **A dark wash is darker than `dark-surface`.** Contrast ratio alone cannot
   express this: a pale wash scores ~10:1 against dark text and reads as a
   glowing slab. Relative luminance is the check that catches it.
2. **The dark ramp ascends.** In light mode the ramp walks warm graphite up to
   the accent, so more colour means more learned. Inverting the canvas without
   re-deriving the ramp reverses that reading, making `stage-1` the brightest pip
   and `stage-5` the dimmest. The dark ramp therefore runs dim graphite
   (`#3C3934`) up to the lifted accent (`#93B2DA`), preserving the same
   direction of meaning.

## Typography

Two families plus a mono. No third family, ever.

**Geist** (already the project preset font) carries the entire interface: nav,
buttons, labels, metadata, form fields, body copy in management screens.

**Newsreader** carries lexicographic content only - headwords, definitions,
example sentences. This is the whole reason a serif exists in the system. If a
string is a piece of dictionary content, it is Newsreader; if it is product
chrome, it is Geist. There is no third rule.

**Geist Mono** carries figures and identifiers: stat numerals (tabular figures
on), IPA transcriptions, keyboard shortcuts, round counters, dates.

Scale, kept deliberately short:

| Token | Use |
| --- | --- |
| `headword` | The word on sense detail and on the exposure card |
| `gloss` | Definitions and example sentences |
| `title` | Page titles, deck names in headers |
| `heading` | Section headings, card titles, question stems |
| `body` | Default interface text |
| `label` | Buttons, nav items, form labels, table cells |
| `label-caps` | Tag text and column headers only |
| `meta-mono` | IPA, dates, round counters, keycaps |
| `numeral` | Single large figures on Today and Progress |

Body copy is capped at `max-w-[65ch]`. Emphasis inside a headline uses italic or
weight of the same family; a serif word is never dropped into a sans line for
visual interest.

**IPA coverage, verified.** The dataset's own transcriptions (`ˈel.ə.kwənt`)
render from Geist Mono, as do the length marks, both affricates written as
digraphs, the script g, the glottal stop, the rhotic schwa and the syllabic
ring. Three characters do not, because Google serves Geist Mono without a Greek
subset and without the combining ranges above U+0333:

| Character | Codepoint | Appears in |
| --- | --- | --- |
| `θ` | U+03B8 | every voiceless dental fricative - *thing*, *both*, *method* |
| tie bar | U+0361 | affricates written `t͡ʃ` rather than `tʃ` |
| `◌̬` | U+032C | the voicing/flap diacritic |

The first is not an edge case, so `meta-mono` carries a per-glyph fallback: the
browser keeps Geist Mono for everything it has and reaches into the next family
only for the missing characters. The stack ends in `serif`, so a machine with
none of the named faces still shows a letter rather than tofu. This is also why
IPA is never given a bare `font-mono` class.

## Layout

Mobile-first. Breakpoints `sm 640 / md 768 / lg 1024 / xl 1280 / 2xl 1536`.

**Mobile (< 768px).** Fixed bottom tab bar, three items, icon over label, each
target at least 44px tall, with `env(safe-area-inset-bottom)` padding. A compact
sticky header carries page title, search, activity, assistant, avatar. Content
is single column at `px-4`. Every multi-column layout in this document declares
its own single-column fallback in the same component file.

**Tablet (768-1023px).** Content gains a second column where the data is
genuinely paired (stat grid, deck item list plus detail). Nav stays bottom.

**Desktop (>= 1024px).** Left navigation rail at 224px, icon plus label, fixed.
Content is `max-w-[1120px]`, left-aligned inside the remaining space, never
centred in the viewport. Assistant opens as a 380px right sidebar that shrinks
the content column rather than overlaying it.

**Study mode is different on purpose.** No rail, no tab bar, no header actions.
Only a round indicator, an exit affordance, and the question stage centred at
`max-w-[640px]` with `min-h-[100dvh]`. `h-screen` is never used anywhere in the
app.

**Vertical rhythm.** This is app spacing, not marketing spacing: `py-8` between
major blocks on mobile, `py-12` on desktop. The 96-128px section padding that
suits an editorial landing page is explicitly rejected here - it would push a
learner's due count below the fold.

## Elevation & Depth

Near-flat. Structure comes from `1px` borders and negative space.

- Default separation: `1px solid border`. Card containers are used only when
  elevation encodes real hierarchy; otherwise groups are separated by
  `divide-y` or by space alone.
- The only shadow in the system: `0 1px 2px rgba(25, 24, 23, 0.04)` on hover for
  interactive cards. Nothing larger. No shadow in dark mode; depth there comes
  from surface lightness steps.
- Focus is a 2px `primary` ring with a 2px offset. It is never removed, and it
  is visible against both canvas and surface in both themes.
- The only backdrop blur is the sticky mobile header, at low strength, with an
  opaque fallback under `prefers-reduced-transparency`.
- Layer order is a fixed named scale, declared once: base 0, sticky header 10,
  bottom nav 20, drawer/sidebar 30, dialog/palette 40, toast 50. No arbitrary
  `z-50` sprinkled at call sites.

## Shapes

One radius system, locked:

- `sm 4px` - inputs, keycaps, CEFR chips, checkboxes.
- `md 8px` - buttons, nav items, choice options, small surfaces.
- `lg 12px` - cards, panels, dialogs, the question stage.
- `pill` - status tags and avatars only.

Nothing larger than 12px on a container. `pill` is never used on a primary
button or a card, so the pill shape reads unambiguously as "this is a status,
not a control".

## Components

Inventory grouped by surface. Everything under "primitive" comes from the
shadcn Base UI registry and is regenerated from these tokens, not hand-styled.

**Primitives (registry).** Button, Input, Textarea, Select, Combobox, Checkbox,
RadioGroup, Switch, ToggleGroup, Field/FieldGroup, Badge, Card, Separator,
Skeleton, Spinner, Progress, Alert, Empty, Tooltip, Popover, Dialog, Sheet,
Drawer, AlertDialog, DropdownMenu, Tabs, Breadcrumb, Command, ScrollArea,
Collapsible, Accordion, Avatar, Kbd, Table, Chart, Toast, MessageScroller,
Message, Bubble, Marker.

**Shell.** `AppShell` (responsive frame), `BottomTabBar` (mobile, 3 items),
`NavRail` (desktop), `AppHeader`, `UserMenu`, `ThemeToggle`,
`CommandPalette`, `ActivityCenter`, `RealtimeIndicator`, `AssistantMount`.

**Vocabulary.** `Headword` (serif, with IPA and inflected forms),
`SenseCard`, `DefinitionBlock`, `ExampleList`, `CefrChip`, `TierChip`,
`RegisterNote`, `CollocationList`, `RelationList` (synonym, antonym, hypernym),
`UsageNote`, `MasteryStage` (named band plus 5-pip ramp),
`ReviewScheduleLine` (next review, interval, review count).

**Library.** `NodeTree`, `NodeRow` (folder, deck, reference variants with item
and due counts), `NodeBreadcrumb` (driven by the server-supplied ancestor
path), `CreateNodeSheet`, `RenameDialog`, `MoveNodeDialog`,
`VisibilityDialog` (with explicit subtree-publication confirmation),
`DeleteNodeDialog`, `DeckSettingsForm` (target words per session, max questions
per round), `DeckItemList`, `AddWordAction`.

**Study.** `SessionRunner` (state machine over the five `/next` states),
`RoundIndicator` (discrete pips, not a percentage bar), `QuestionStage`,
`ExposureCard` (flashcard, `interactionMode: exposure`, unanswerable),
`SingleChoiceQuestion`, `TextSpanQuestion` (blank plus word bank),
`FreeTextQuestion`, `CalibrationNote` (requested vs served level, and the
consequence when `isFallback` is true), `VerdictPanel` (correct, incorrect,
reveal payload, mastery before and after), `PendingGradePanel` (awaiting the
task snapshot), `RoundBreakPanel`, `PreparingPanel`, `SettlingPanel`,
`SessionRecap` (client-accumulated, since the backend has no summary endpoint).

**Progress.** `StatFigure`, `DueForecastChart` (7 day), `MasteryDistribution`,
`CefrMixChart`, `ReviewHistoryChart` (day buckets), `WeakestWordList`.

**Assistant.** `AssistantSurface` (drawer on mobile, sidebar on desktop),
`ThreadList`, `ThreadTranscript`, `StreamingMessage`, `ToolCallTrace`,
`ApprovalRequestCard` (move, publish, delete, sense removal),
`RunRecoveryNotice`.

**Every interactive component ships four states.** Idle, loading (skeleton
shaped like the real content, never a bare spinner), empty (composed, with the
action that populates it), error (inline for forms, contextual banner for
sections, toast only for transient failures). A component delivered with only
its success state is not delivered.

## Do's and Don'ts

**Do**

- Set dictionary content in Newsreader and interface chrome in Geist. Nothing in
  between.
- Name mastery bands with the five stage names. They come from real backend
  thresholds.
- Show round structure as discrete counted pips, matching the backend's actual
  round mechanic.
- Say out loud when a difficulty fallback occurred and what it costs, and when a
  realtime connection is down and results may be stale.
- Keep the accent identical on every screen. One accent, whole product.
- Declare the mobile fallback in the same file as any multi-column layout.
- Gate every animation on `prefers-reduced-motion`.
- Use `Empty`, `Alert`, `Skeleton`, `Badge`, `Separator` from the registry rather
  than styled divs.

**Don't**

- No em dash anywhere a user can see it. Headlines, labels, body, tooltips,
  captions, alt text, button text. Use a comma, a period, or a plain hyphen.
- No raw difficulty numbers ("Level 3 of 4") shown to the learner. Translate to
  a calibration statement.
- No rainbow mastery scale, no gradient fills, no glow, no glassmorphism beyond
  the single mobile header blur.
- No pure `#000000` or `#FFFFFF` as text colour, no `bg-*` shadows heavier than
  the one hover shadow.
- No `space-y-*` or `space-x-*`. Flex or grid with `gap-*`.
- No manual `dark:` colour overrides at call sites. Semantic tokens only.
- No landing-page grammar: no hero blocks, no marquees, no scroll hijacking, no
  uppercase eyebrow label above every section, no `window.addEventListener`
  scroll handlers.
- No settings control wired to an endpoint that does not affect behaviour. If a
  control cannot change anything, it does not ship.
- No placeholder-as-label, ever. Labels sit above their input.
- No emoji in code, markup, or visible copy.
- No icon library other than Phosphor, and no hand-drawn SVG icon paths.

## Implementation Notes

**Stack, as verified in the workspace.** Next.js 16.2.6 App Router (RSC on),
React 19.2.4, Tailwind v4 with tokens in `app/globals.css` via `@theme`,
shadcn config `style: base-nova`, `base: base` (Base UI primitives, so custom
triggers use `render`, not `asChild`), preset `b2fA`, `importAlias: @`.

**Three deliberate changes to the current config.**

1. `iconLibrary` moves from `lucide` to `phosphor` (`@phosphor-icons/react`),
   set once in `components.json` so the registry rewrites imports. Phosphor's
   bold weight matches the slightly technical stroke this system wants.
2. Toasts move from `sonner` to the Base UI `toast` component, because this
   project's `base` is `base`.
3. `fontHeading` is set to Newsreader via `next/font/google`, exposed as
   `--font-serif`, alongside the existing Geist and Geist Mono variables.

**Cache Components stays off.** Every screen in this product renders
per-user authenticated data, so `use cache` has almost no surface to work on
while `cacheComponents: true` would force `Uncached data was accessed outside
of <Suspense>` build failures across the whole app for no benefit. Streaming
uses plain `<Suspense>` with `loading.tsx`, and `unstable_instant` is
consequently not applicable.

**Next 16 conventions that differ from older App Router habits.** `proxy.ts`
replaces `middleware.ts` and already exists. `params` and `searchParams` are
Promises and must be awaited in pages, layouts, and route handlers.

**The retained layer.** `lib/api/*`, `lib/auth/*`, `lib/realtime/*`, `proxy.ts`,
and the `app/api/*` BFF routes are architecturally correct: bearer tokens never
leave the server, and they are sealed in an encrypted `HttpOnly` iron-session
cookie. They are kept. The data-access layer above them (`lib/query`,
`lib/actions`, `lib/stores`) is rewritten, and the entire presentation layer is
replaced.
