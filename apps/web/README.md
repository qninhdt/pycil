# Bauhaus — Form & Function

Pycil's Next.js web application and design showcase.

## Run

From `apps/web/`, using the current pnpm workspace/lockfile:

```sh
pnpm install
pnpm run dev
```

Open the URL printed by Next.js. In development, the mock data mode needs no API server or database.

```sh
pnpm run build    # TypeScript checks + production build
pnpm run lint     # Oxlint
pnpm exec playwright install chromium
pnpm run test
```

The browser suite starts its own Next.js server on `127.0.0.1:4173`. For a preinstalled Chromium, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable. To retain the visual matrix outside ignored `test-results/`, set `SHOWCASE_SCREENSHOT_DIR`.

## Explore

- **Components:** interactive groups covering the installed controls, overlays, navigation, feedback, calendar and chart.
- **Artwork and Icons:** authored motifs, backgrounds and icons, with color and mono previews and copyable usage.
- **Foundations:** the approved palette, typography and six geometric building blocks.
- **Compositions:** six larger examples, including cards, metrics, carousel, reveal, resizable panes and authentication layout.

The sidebar jumps to specimens; catalog search filters them. `Ctrl/⌘ K` or the header search button opens global navigation. The theme toggle persists via `bauhaus-theme`; the root layout applies the saved mode before hydration. Copy buttons offer selectable source when clipboard permissions are denied.

## Maintain the theme

The root [`DESIGN.md`](../../DESIGN.md) is the palette authority. The showcase does not redefine the product's learning-status semantics.

| Location | Responsibility |
| --- | --- |
| `src/app/globals.css` | Canonical palette literals, Tailwind theme, semantic color roles and global treatments |
| `src/components/ui/` | Official shadcn source; primitive behavior and component variants |
| `src/components/artwork/` | Authored paths, typed names and shared SVG renderers |
| `src/components/showcase/` | Catalog examples, composition frames, source and copy affordances |
| `src/components/application/` | Application shell and account controls |

Do not add palette literals to JSX or invent dark-mode colors. Dark mode remaps the existing palette. Decorative colors do not acquire universal functional meanings. Small red action labels use Pomegranate/Clouds for contrast; blue actions use an alpha fill with semantic text. Dark destructive actions retain a red outline with readable foreground text. Saturated art stays unchanged. The favicon is derived from the rendered `BrandMark` and CSS tokens.

Reuse art directly:

```tsx
import { Icon, Motif, Background } from '@/components/artwork/artwork'

<Icon name="collection" tone="color" />
<Motif name="orbit" tone="mono" />
<Background name="corner-study" />
```

SVGs are decorative (`aria-hidden`). Keep labels in the surrounding UI. Clip large backgrounds in a positioned region, and reserve a separate area for text. Exported name catalogs drive gallery counts; no generator or randomized artwork is used. Code previews are concise usage examples, not complete application implementations.

Install additional primitives with the official CLI (`pnpm exec shadcn add <component>`), then inspect diffs: existing components contain intentional customizations. Add a reachable specimen and verify both themes, keyboard interactions and mobile layout.

## Verification and limitations

The production build, TypeScript check and Chromium suite cover the application, showcase, icon system, responsive layouts, and key interactions. Oxlint reports warnings but no errors. The browser suite is not a full accessibility audit or cross-browser certification.

Oxlint currently reports Fast Refresh mixed-export and state-in-effect warnings. No rule is disabled.
