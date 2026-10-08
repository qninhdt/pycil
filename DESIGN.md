---
version: alpha
name: Pycil Bauhaus Learning System
description: A desktop-first language-learning interface built from strict editorial grids, oversized geometric typography, and a red-blue-yellow Bauhaus status system.
colors:
  primary-red: "#E74C3C"
  primary-blue: "#3498DB"
  primary-yellow: "#F1C40F"
  red-dark: "#C0392B"
  blue-dark: "#2980B9"
  yellow-dark: "#F39C12"
  ink: "#2C3E50"
  ink-soft: "#34495E"
  text-muted: "#7F8C8D"
  text-subtle: "#95A5A6"
  border: "#BDC3C7"
  canvas: "#ECF0F1"
  success: "#27AE60"
  teal: "#1ABC9C"
  purple: "#9B59B6"
  red-soft: "#E74C3C1A"
  blue-soft: "#3498DB1A"
  yellow-soft: "#F1C40F1F"
  ink-overlay: "#2C3E507A"
typography:
  display-xl:
    fontFamily: Manrope
    fontSize: 72px
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: -0.045em
  display-lg:
    fontFamily: Manrope
    fontSize: 56px
    fontWeight: 800
    lineHeight: 1
    letterSpacing: -0.04em
  headline-lg:
    fontFamily: Manrope
    fontSize: 40px
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: -0.035em
  headline-md:
    fontFamily: Manrope
    fontSize: 32px
    fontWeight: 750
    lineHeight: 1.1
    letterSpacing: -0.025em
  headline-sm:
    fontFamily: Manrope
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: -0.02em
  body-lg:
    fontFamily: Manrope
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.5
  body-md:
    fontFamily: Manrope
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  body-sm:
    fontFamily: Manrope
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.45
  label-lg:
    fontFamily: Manrope
    fontSize: 15px
    fontWeight: 650
    lineHeight: 1.2
  label-md:
    fontFamily: Manrope
    fontSize: 13px
    fontWeight: 650
    lineHeight: 1.2
  label-caps:
    fontFamily: Manrope
    fontSize: 12px
    fontWeight: 600
    lineHeight: 1
    letterSpacing: 0.22em
spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  3xl: 64px
  4xl: 96px
  page-x: 32px
  page-y: 24px
  section: 32px
  gutter: 16px
rounded:
  none: 0px
  xs: 2px
  sm: 4px
  md: 6px
  full: 9999px
components:
  page-canvas:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.xs}"
    padding: 14px
    height: 48px
  button-primary-hover:
    backgroundColor: "{colors.ink-soft}"
  button-review:
    backgroundColor: "{colors.primary-red}"
    textColor: "{colors.canvas}"
    rounded: "{rounded.xs}"
    padding: 14px
    height: 48px
  button-review-hover:
    backgroundColor: "{colors.red-dark}"
  button-outline:
    backgroundColor: transparent
    textColor: "{colors.ink}"
    rounded: "{rounded.xs}"
    padding: 14px
  input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: 48px
  input-focus:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
  chip:
    backgroundColor: "{colors.border}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.full}"
    padding: 8px
  status-due:
    backgroundColor: "{colors.red-soft}"
    textColor: "{colors.primary-red}"
    rounded: "{rounded.full}"
    padding: 8px
  status-not-yet-due:
    backgroundColor: "{colors.blue-soft}"
    textColor: "{colors.primary-blue}"
    rounded: "{rounded.full}"
    padding: 8px
  status-new:
    backgroundColor: "{colors.yellow-soft}"
    textColor: "{colors.yellow-dark}"
    rounded: "{rounded.full}"
    padding: 8px
  panel:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    padding: 24px
  modal:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: 24px
---

# Pycil Design System

## Overview

Pycil uses a **Bauhaus-inspired editorial interface** for a language-learning product. The visual system is strict, geometric, high-contrast, and intentionally flat. It should feel more like a modernist poster, Swiss editorial grid, or museum identity translated into software than a conventional rounded SaaS dashboard.

The defining visual signature is the repeated combination of **three primary colors and three primary shapes**:

- **Red circle** = urgency, review, due material, primary momentum.
- **Blue square** = established knowledge, active learning state, not-yet-due material, information.
- **Yellow triangle** = new material, discovery, future learning.

These shapes are not decorative afterthoughts. They are part of the product language and should reappear in navigation, status summaries, page headers, flashcards, profile visuals, progress views, and empty-state composition.

The UI should feel **structured rather than soft**: thin divider lines, large typography, deliberate asymmetry, cropped geometric forms, and strong alignment are preferred over shadows, glass effects, gradients, rounded cards, or floating pills.

Pycil is information-dense but never visually noisy. Hierarchy comes from scale, weight, alignment, line work, and the red/blue/yellow system.

## Colors

All UI colors must come from the **Flat UI Palette v1 (`defo`)**. Do not introduce unrelated hex colors. Alpha variants of these palette colors are allowed for soft fills and overlays.

### Core brand triad

- **Primary Red — Alizarin (`#E74C3C`)**: due states, review actions, active navigation emphasis, urgent counts, red circles, and high-priority learning moments.
- **Primary Blue — Peter River (`#3498DB`)**: not-yet-due states, selected/active informational elements, progress, blue squares, links, focus states, and secondary emphasis.
- **Primary Yellow — Sun Flower (`#F1C40F`)**: new content, learn actions, yellow triangles, discovery cues, and optimistic forward-looking accents.

These three colors should dominate all branded visuals. A screen can use all three at once, but only one should dominate an interaction hierarchy.

### Supporting palette

- **Midnight Blue (`#2C3E50`)**: default text and near-black substitute. Do not use pure black.
- **Wet Asphalt (`#34495E`)**: secondary text and hover state for dark controls.
- **Asbestos (`#7F8C8D`)**: metadata, captions, inactive labels.
- **Concrete (`#95A5A6`)**: tertiary text and disabled states.
- **Silver (`#BDC3C7`)**: borders, dividers, inactive progress tracks.
- **Clouds (`#ECF0F1`)**: page canvas and flat surfaces. Do not use pure white as a general surface color.
- **Pomegranate (`#C0392B`)**: red hover/pressed state.
- **Belize Hole (`#2980B9`)**: blue hover/pressed state.
- **Orange (`#F39C12`)**: yellow hover/pressed state and yellow text when stronger contrast is needed.
- **Nephritis (`#27AE60`)**: success-only semantic feedback; use sparingly.
- **Turquoise (`#1ABC9C`)** and **Amethyst (`#9B59B6`)**: optional tertiary data-viz categories only. Never compete with the primary red/blue/yellow identity.

### Semantic mapping

The vocabulary-learning status system is fixed:

| Status | Shape | Color | Meaning |
| --- | --- | --- | --- |
| Due | Circle | Alizarin | Needs review now |
| Not yet due | Square | Peter River | Learned and scheduled for later |
| New | Triangle | Sun Flower | Not learned yet |

Never rely on color alone. Status text or shape must always accompany the color in functional contexts such as tables, charts, legends, and cards.

Soft status backgrounds may use alpha variants such as `#E74C3C1A`, `#3498DB1A`, and `#F1C40F1F`, but the main icon/shape remains fully saturated.

## Typography

Use **Manrope** throughout the application. The interface depends on a clear contrast between oversized, heavy display typography and restrained utility text.

- **Display typography** is bold, tight, and architectural. Use weights 750–800 with negative tracking. Large headings such as `Dictionary`, `TOEIC 800`, profile names, and study prompts should be visually dominant.
- **Section headings** use 24–32px, bold or semibold.
- **Body copy** stays at 14–18px with comfortable line-height and no decorative tracking.
- **Micro-labels** may be uppercase with wide letter spacing for poster-like accents such as `PRACTICE`, `PROGRESS`, or `TAP TO REVEAL`.
- **Numbers are design elements.** Large counts such as `500`, `1,240`, `42`, or streak values may use the same weight and scale as headlines.

Avoid mixing multiple font families. Do not use serif, handwriting, mono, or display novelty fonts in normal UI.

## Layout

Pycil uses a **strict grid-first desktop layout**. The grid is visible through alignment, 1px rules, section boundaries, and repeated columns. The product should feel intentionally composed, not card-stacked.

### Global rules

- Base spacing follows an 8px rhythm with 4px micro-adjustments.
- Primary page padding: 24–32px.
- Standard content gaps: 16px.
- Major section gaps: 24–32px.
- Use **1px divider lines** aggressively to create structure.
- Prefer full-width sections separated by rules over isolated floating cards.
- Keep page content visually dense enough that large blank areas feel intentional, not accidental.
- Align major headings, tables, charts, and action controls to shared vertical guides.
- Decorative shapes may intentionally crop against panel or viewport edges.

### Application shell

Desktop uses a fixed left sidebar approximately 260–300px wide. The sidebar is a composition, not a generic navigation panel:

- Brand/logo zone at top.
- Five primary navigation entries, in order: Home, My Library, Published, Discovery, Dictionary.
- Each entry owns a geometric icon.
- Active navigation should use either a red full-width field or a restrained red indicator with a soft status wash.
- A large `New deck / folder` action occupies its own architectural block.
- User/account block is anchored at the bottom.
- Sidebar sections are separated with full-width 1px rules.

For pages explicitly designed as independent fullscreen experiences—authentication, flashcards, focused study modes—do not render the sidebar.

### Page headers

Deck, folder, dictionary, and profile pages use large header zones with a strong title on the left and a geometric composition on the right. Decorative geometry should reuse circles, squares, triangles, arcs, and black/ink construction lines.

Page header geometry may extend beyond its local cell but must remain clipped by the page frame. Do not use illustrations, 3D art, or gradients as substitutes.

### Responsive behavior

- **Above 1200px:** preserve the full editorial desktop composition.
- **768–1199px:** collapse wide statistic bands and multi-column areas into two columns; reduce decorative geometry before reducing information hierarchy.
- **Below 768px:** switch the sidebar to a compact mobile navigation pattern, stack page headers, convert dense tables to list rows/cards, and make fullscreen study surfaces edge-to-edge.
- Never shrink desktop typography uniformly. Rebuild hierarchy at each breakpoint instead.

## Elevation & Depth

The system is fundamentally **flat**. Depth is created by lines, scale, color fields, and containment rather than shadows.

- Default panels use no box shadow.
- Borders and section rules are preferred to floating cards.
- Hover states should change fill, border, or text color rather than lift the element.
- Modals are the main exception: use a `Midnight Blue` alpha backdrop and a restrained surface separation. The modal itself remains visually flat.
- Avoid blur, glassmorphism, frosted panels, neon glows, or layered gradient shadows.

## Shapes

The geometry system is as important as the color system.

### Primary shapes

- **Circle + Red**: use as full circles, half circles, quarter circles, or cropped arcs.
- **Square + Blue**: use as solid blocks, vertical bars, or cropped rectangles.
- **Triangle + Yellow**: use as right triangles or equilateral triangles, frequently entering from a corner.

Do not arbitrarily swap shape/color pairings in branded or semantic UI. The pairing should become recognizable across the product.

### Construction lines

Thin `Midnight Blue` rules may intersect shapes, extend across panels, or divide geometric fields. These lines evoke grid construction and should feel precise rather than decorative.

### Corner radius

The interface is deliberately sharp:

- Containers: 0px by default.
- Buttons and inputs: 2–4px.
- Large modals: up to 6px.
- Pills are permitted only for tags, compact filters, status chips, and toggles.
- Never apply large 12–24px radii to general cards or layouts.

### Icons

Use the authored `Icon` component in `apps/web/src/components/artwork/artwork.tsx` throughout the app. Its 107 icons have paired custom `color` and `mono` drawings built from the same silhouette, axes, and cuts. Identity and learning icons use a 48-unit grid; controls use a 24-unit grid. Color fills functional geometric planes. Mono uses one ink color, with solid planes, negative space, and open linework chosen per icon; it must not turn every colored area into another outline. Compact controls default to mono. No external icon library is installed. The SVG supplies its default size through `width` and `height` attributes so a button, field, or local class can set its own size without a global CSS override. The Showcase Icons catalog displays both drawings side by side at product sizes.

## Components

### Buttons

**Primary action:** dark `Midnight Blue` fill with `Clouds` text, near-square corners, clear arrow or icon when it improves directionality.

**Review / urgent action:** `Alizarin` fill with `Clouds` text. Use only when the action is meaningfully associated with review, due work, or an urgent learning task.

**Secondary action:** transparent or `Clouds` surface, 1px `Silver` or `Midnight Blue` border, `Midnight Blue` text.

**Ghost/text action:** no border, text only, typically blue for navigation or ink for neutral controls.

Buttons should not be pill-shaped. Heights generally range from 44–52px on desktop.

### Inputs and search

- Flat `Clouds` surface.
- 1px border; use `Peter River` for focus.
- Radius 4px or less.
- Search fields may include a left search icon and right clear button.
- Filters can sit directly beside the field as compact bordered controls.
- Autocomplete suggestions use compact pills below the input, but only for search terms or filters.

### Tabs

Tabs are text-first. Use a strong bottom rule for the active tab rather than a filled rounded segment. Typical tabs: `Overview / Words`, `Verb / Noun / Phrasal verb / Idiom`.

### Status chips

Status chips are compact pills because they encode metadata, not structure. Each contains the matching status shape or dot when space allows.

- Due: red soft field + red text/shape.
- Not yet due: blue soft field + blue text/shape.
- New: yellow soft field + orange/yellow text + yellow triangle.

### Tags

Neutral tags such as `Business`, `TOEIC`, `Intermediate`, `Private`, or part-of-speech labels use `Silver` or `Clouds` fields with `Ink Soft` text. They should be visually quieter than status chips.

### Cards and panels

Do not default to generic rounded cards. A panel should usually be a rectangular area defined by one or more 1px rules.

When a reusable card is needed—folder preview, published folder, learning module—use:

- 0–4px radius.
- 1px border.
- Clear internal grid.
- One cropped geometric accent in a corner or edge.
- Strong typographic title.
- Minimal or no shadow.

### Assistant interface primitives

Assistant interface primitives live in `apps/web/src/components/ui`. Messages, bubbles,
markers, attachments, the message scroller, and questionnaires use the same flat
surfaces, thin rules, sharp corners, and clear keyboard focus as the rest of the
system. Their interactive variants and states are visible in the Showcase catalog.

### Metric bands

Deck and folder pages often begin with a wide status band containing:

- Total word count.
- Horizontal red/blue/yellow progress bar.
- Three status counts with matching geometry.
- Optional structural counts such as subfolders or decks.

Metrics should be separated with vertical rules rather than individual cards.

### Learning action tiles

Use three horizontally aligned modules:

1. `Flashcards` — blue square/block accent.
2. `Learn` — yellow triangle/corner accent.
3. `Review` — red circle/arc accent and red due count.

Each tile contains a numeric index (`01`, `02`, `03`), large label, supporting count, and directional arrow.

### Data tables

Tables are flat, full-width, and line-driven:

- Use horizontal rules instead of boxed rows.
- Strong word/title column.
- Muted secondary definition/metadata text.
- Status chips use the canonical red/blue/yellow mapping.
- Bulk selection uses simple outline checkboxes.
- Row menus use compact ellipsis controls.
- Avoid zebra striping unless density makes scanning impossible.

### Dictionary results

The dictionary page uses a large search-first header. Selecting a search result updates the reading pane without changing the route. A selected word block contains available pronunciation, alternate spellings, a sense count, and part-of-speech tabs. Each sense shows the available CEFR level, tier, register, examples, usage note, spelling and inflected forms, patterns, collocations, and linked meanings. Individual senses are numbered (`01`, `02`, `03`) and vertically separated by rules. Available entries offer a preparation action and show generation status before their senses appear.

Each sense should show:

- Sense number.
- Status geometry where applicable.
- Definition as the strongest line.
- Grammar/register metadata as small neutral tags.
- All example sentences supplied with the sense.
- `Add to deck` action aligned to the right.
- Existing deck presence shown as quiet metadata below the action.

The optional right rail contains progress, decks containing the word with the number of its senses in each deck, and related words. Each sense also shows its own deck count and the deck names, so membership remains visible while reading. It should feel like a continuation of the same grid, not a detached card stack.

`Add to deck` opens the reusable folder/deck destination dialog. The dialog supports Personal and Published spaces, search, breadcrumbs, and creating a deck in the current folder. A selected meaning is added with a membership delta; deck creation sends its initial senses with the create request.

### Add-words modal

The add-words flow is a large centered modal with two panes:

- Left: search, filters, grouped word/sense results, checkboxes.
- Right: selected senses, removable one by one.
- Bottom-right: strong `Add to deck` action.

Keep the modal wide and utilitarian. Use borders and vertical rules to separate panes. Avoid excessive nested cards.
An owned deck's meaning detail offers `Remove from deck`; adding and removing use membership deltas rather than a full deck editor.

### Deck and folder views

Deck and folder pages share a common architecture:

- Breadcrumb.
- Oversized title.
- Metadata line.
- Tag row if relevant.
- Geometric header motif.
- Status band.
- Flashcards / Learn / Review action strip.
- `Overview / Words` tab system.

Folder overview then exposes `Subfolders` and `Decks` as structured lists/cards. Deck `Words` view uses the table pattern.

Library routing is path-based: `/app/personal/<node_id>` opens the learner's Personal tree, while `/app/u/<owner_id>/published` and `/app/u/<owner_id>/published/<node_id>` open an author's Published tree. Node routes default to Overview and append `/words` for Words. My Library points to the Personal root; Published points to the current user's Published root. Another author's Published route highlights Discovery. The Personal root has no Personal/Published switch; each space has its own menu entry. Breadcrumbs start with `Personal`, `Me > Published`, or `<author name> > Published`, according to ownership. Author attribution reads `Me` for the current user. Node links use `libraryHref`, `publishedHref`, or `nodeHref` according to the node's space and owner. The `/app/library` route is removed.

Word tables show Word, Definition, Status and Last reviewed; there is no Source decks column. Provenance remains in word detail. Overview/Words tab triggers have no outer focus frame; keyboard focus uses an underline and subtle fill.

Library uses the available shell width with compact headers, summary bands and list rows. References retain the target's visual identity: `deck-reference` and `folder-reference` reuse the corresponding deck/folder artwork with a small corner-arrow marker. Folder references appear with subfolders; deck references appear under `Decks`. There is no standalone chain-link reference icon. Unavailable targets use a neutral document rather than a guessed type.

Folder and deck cards share a rectangular layout with a stable motif that clips to the bottom and right edges. The same motif appears beside the title in node detail. Authors appear on cards and detail. Folder contents support card and list views; the choice persists in local storage. The sidebar New action opens creation with an editable destination, while a contextual New action shows a fixed parent. Node menus expose edit, move, copy, and delete flows; unsupported live backend mutations surface their API error without a mock fallback.

Deck Overview keeps a flashcard preview beside concise deck details. The reusable controlled component lives at `apps/web/src/components/learning/flashcard.tsx`; it owns presentation only. Its front and back follow `tmp/flashcard_1.png` and `tmp/flashcard_2.png`: oversized centered word on the front; smaller lexical header, numbered meaning, definition and examples on the back. Both faces share one adaptive background with a uniform translucent canvas overlay beneath the text. Card size and the single POS label remain stable when flipping. Click either face to flip it; previous/next controls stay outside the card, with no Next card or Show word buttons inside. Navigation is manual, not a slideshow. The card and its navigation controls have square corners. Library supplies the data and preview navigation, with no learning submission. Backend target markup is rendered by the shared `MarkedText` component, never as raw HTML or guessed headword matches. Audio, translation and difficult-marking are not fabricated.

Bottom New/account menu triggers use an inset keyboard indicator instead of an outer focus outline. Sign out uses a dedicated Bauhaus door-and-arrow icon.

Flashcard backgrounds are selected deterministically per sense ID from the existing 16 authored compositions through `apps/web/src/lib/flashcard-artwork.ts`. There is no procedural artwork generator; backgrounds can repeat because the catalog is finite. The same sense retains its selection across decks, sorting, both faces and reloads. `Background` adapts its SVG canvas to the measured container ratio, re-anchors the authored shapes and extends construction rules. All shapes scale uniformly: no cover crop, contain letterbox or nonuniform stretching. Every background, including `inverse-poster`, uses the theme-aware canvas token for its base.

### Focus mode

`/focus/flashcards?node=<node_id>` and `/focus/learn?node=<node_id>&selection=<DUE|NEW|AUTO>` are fullscreen routes without the app sidebar. Home and Library launch them with the current scope. Flashcards use the existing word card and preserve the current card and revealed face in local storage; they do not submit scheduler results. Previous/next controls remain outside the card.

Quiz mode prepares questions using the user's learning settings, then presents the seven backend question types through choice, single-word, or short-answer controls as permitted by the prepared format. Each question has a deterministic art background with a translucent overlay. Questions are grouped into rounds of up to eight. A miss or partial answer returns in the next round, with at most three attempts per question. Round recaps show cleared and returning questions. The final recap shows one Again/Hard/Good/Easy rating per sense and whether its scheduler result was applied.

The quiz session, feedback, round position, and pending submission persist locally for the signed-in account. Reloading resumes the same question. Only a completed session submits a review batch; retries reuse the same idempotency key. Choice answers are checked against the prepared correct option; typed answers use `/study:grade` and display its detailed feedback. If saving locally fails, the UI stops progress and asks the user to restore browser storage.

### Profile

The public profile lives at `/u/{handle}` (or `/u/{id}` before a handle is set); nested
Published folders and decks have shareable child routes. `/app/profile` opens the
signed-in person's public profile. Any visitor may read a profile without signing in.

- Large name and handle.
- Compact bio and joined date.
- Share action for everyone; edit handle and bio only for the owner.
- Browsable Published folders and deck meanings using the library's geometric visual language.
- No study history, streak, due counts, personal settings, or private library data on a public profile. The current public API does not expose those reference-image sections.

### Settings

Settings is a separate signed-in route at `/app/settings`, reached from the account menu.
General covers interface language, translation language, and time zone. Learning covers
seven question types, all three response formats (`SINGLE_CHOICE`, `SINGLE_WORD`,
`SHORT_ANSWER`), session depth, and explanations. The saved selection comes from
`/v1/me`; the form uses returned pair availability and limits. Typed formats show the
plan restriction when advanced grading is unavailable. Changes are saved together
through `PATCH /v1/me/settings`.
Each question type and answer format has its own semantic Bauhaus icon in Learning;
the visible label and separate selection check remain the primary state cues.

### Authentication

Authentication is a fullscreen independent page with a split layout:

- Left: brand manifesto / editorial poster panel with very large typography, construction lines, and oversized red/blue/yellow shapes.
- Right: login or signup form.
- Form controls remain simple and rectangular.
- General submit button uses `Midnight Blue`; social login uses an outline treatment.
- Do not display the app sidebar on authentication pages.

### Empty, loading, and error states

- Empty state: one large geometric motif + concise headline + one clear action.
- Loading: use simple bars or skeleton blocks aligned to the existing grid; no playful bouncing blobs.
- Error: red is permitted but pair it with text/icon, never color alone.
- Success: use Nephritis sparingly and only for explicit completion feedback.

### Motion

Motion is functional and short:

- 120–180ms for hover/focus transitions.
- 180–240ms for panels, drawers, or modal entrances.
- Use ease-out movement; avoid springy overshoot.
- Geometric brand shapes do not continuously float, pulse, or rotate.
- Progress changes may animate linearly but should settle quickly.

## Do's and Don'ts

- **Do** preserve the red circle / blue square / yellow triangle system across all screens.
- **Do** use the Flat UI Palette v1 colors only; alpha variants are acceptable.
- **Do** use `Midnight Blue` instead of pure black and `Clouds` instead of generic white surfaces.
- **Do** rely on thin rules, alignment, scale, and geometry for hierarchy.
- **Do** keep corners sharp and radii minimal.
- **Do** use oversized bold headings where a page has a clear single subject.
- **Do** make data-heavy areas feel editorial and structured rather than card-heavy.
- **Do** keep due/not-yet-due/new semantics consistent everywhere.
- **Do** ensure status meaning remains understandable without color.
- **Do** maintain accessible text contrast; if a bright fill cannot support small light text, use `Midnight Blue` text instead.
- **Don't** introduce gradients as a default visual treatment.
- **Don't** use glassmorphism, glossy effects, strong drop shadows, or neon glows.
- **Don't** use large rounded cards, bubble-like controls, or pill-shaped primary buttons.
- **Don't** add random pastel colors or new brand hues outside the approved Flat UI palette.
- **Don't** swap the semantic shape/color pairs for visual variety.
- **Don't** fill every empty area with decoration; geometry should reinforce composition and hierarchy.
- **Don't** redraw the sidebar in focused/fullscreen experiences unless navigation is explicitly required.
- **Don't** use generic dashboard card grids when a ruled section, metric band, table, or editorial split layout is more appropriate.
