# Bauhaus — Form & Function

Pycil's Next.js web application and design showcase.

## Run

From `apps/web/`, using the current pnpm workspace/lockfile:

```sh
pnpm install
pnpm run dev
```

Open the URL printed by Next.js. In development, the mock data mode needs no API server or database.

For live authentication, set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` in
`apps/web/.env.local` for the same Clerk instance used by the API, and use
`NEXT_PUBLIC_DATA_MODE=live`. The frontend uses `@clerk/nextjs` and Clerk request protection in `src/proxy.ts`;
server account loading also requires the matching `CLERK_SECRET_KEY`. Clerk issues the
session token, which the frontend sends as a bearer token directly to the API at
`NEXT_PUBLIC_PYCIL_API_URL` (default `http://127.0.0.1:8000`), under `/v1/*`.
Server reads prefer the server-only `PYCIL_API_URL` when configured, then the public API address. Set `NEXT_PUBLIC_PYCIL_API_URL` separately when the backend has a private server address. The API verifies
the token using Clerk's public JWKS; `ALLOWED_ORIGINS` must include the web origin.
The frontend loads its own environment files and does not load the root `.env`.
Signed-in visitors to `/login`, `/signup` and `/forgot-password` are redirected to
their safe `/app` return route, or `/app` by default. Pending Clerk account tasks
continue at `/auth/continue`; credential forms wait for the session to load.

The application scrolls inside its workspace pane. Navigating to another page
starts at the top; Back/Forward restores the position of that history entry.
Restoration waits for loaded content when necessary and stops on user input.
Automatic scroll anchoring is disabled in this pane so content updates cannot
shift the restored position. The assistant keeps its own independent scrolling.

```sh
pnpm run build    # TypeScript checks + production build
pnpm run lint     # Oxlint
node node_modules/@playwright/test/cli.js install chromium
pnpm run test
```

Testing uses unit, integration and E2E levels. See [test ownership and commands](tests/README.md). For a preinstalled Chromium, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable.


## Rendering and state ownership

Routes and layouts render initial data from Pycil on the server. Interactive domain
views receive a matching dehydrated TanStack cache with 60 seconds of freshness.
Filters, cursors, selection and ordinary mutations call Pycil directly from the
browser; Next.js has no CRUD forwarding endpoints or Server Actions. Same-page
controls update native history so Back, Forward and reload retain the current URL.

The browser cache is scoped to the active Clerk session and cleared on a session
change. Account display and settings use the canonical account query. Initial
account content renders before the Clerk browser SDK finishes loading; operations
requiring its token wait for the SDK.

The `pycil-theme` cookie owns light/dark rendering. NextIntl owns locale messages;
the locale cookie, Accept-Language and English fallback determine server rendering.
Successful settings saves and `/auth/complete` synchronize the saved locale cookie.
The completion route writes Next.js-owned preferences and redirects; it is not a
backend API proxy. Personal and own Published material use `/app/personal` and
`/app/published`; public profiles and collections use `/u/[identifier]`.

Domain views live in `src/features/{home,account,auth,library,vocabulary,study,assistant}`.
Shared controls, artwork and shell live in `src/components`. Shared HTTP, identity,
query and preference boundaries live in `src/lib/{api,auth,query,preferences}`.

## Landing page

`/` is the public Bauhaus landing page; `/app` opens the learning application.
The landing page's English learning worksheet lets visitors choose a meaning of
“bank” and try its contextual question. It is a labeled local example: it does
not save Library changes or submit learning progress. Signup and sign-in actions
use the existing `/signup` and `/login` routes.

The page uses Tailwind, shared palette tokens, artwork and shadcn buttons. Static
content lives in `src/components/landing/landing-page.tsx`; the interactive example
lives in `learning-map.client.tsx`. Run `pnpm exec playwright test landing.test.ts --project=integration`
for interaction, navigation, responsive and theme checks.

## Live integration and E2E

Home, account/settings, Library, Dictionary, study/flashcards and PycilAI use the
live service adapter. Discovery reads the public catalog. Library edits use atomic
sense deltas and metadata patches; move, copy, publish/unpublish and saved references
use the [backend Library contracts](../../docs/backend/modules/library.md).
Public creation/publication requires explicit confirmation. Viewing flashcards does
not submit reviews. Accepted reviews invalidate progress/reporting queries.

Practice, Learn new and Review enter `/app/learn` directly from Home or any
Library scope. Signed-out visitors can read Published folders/decks and public
meanings through the same canonical links, without personal learning details.
Preparation runs inside focus mode; failures use an accessible popup
with Retry and Back to My Library. Leaving preparation cancels the browser request.
Storage failures stop advancement and show recovery instead of silently losing answers.

Use **Create reference** in a folder/deck's menu, after **Copy**, to name a live
link and choose its destination. This is also available for other users' Published
material. A Published reference links to its original folder/deck. Private sources
can be saved in Personal; Published sources can also be saved in Published with
explicit confirmation.

Product browser E2E lives in the independent root [`e2e/`](../../e2e/README.md)
package. From the repository root:

```sh
pnpm --dir e2e test
pnpm --dir e2e test:live
```

The default profile uses production Next.js, the real API, disposable PostgreSQL/
Redis, real development Clerk, and a controlled external model boundary. Live is
three fixed model journeys. E2E owns its explicit ignored credentials, per-test
actors/scenarios and private diagnostics; it does not read application dotenv files.
See its README for setup, mobile/WebKit, external-auth prerequisites and cleanup.

Frontend `pnpm test` owns unit and browser/service integration only. The `Tests`
workflow runs these checks and the separate root E2E job on trusted changes.
Fork PRs cannot use development identity secrets; a skipped job is missing coverage.
A manual `live_provider` input adds paid checks after the default profile.

## Explore

- **Components:** interactive groups covering the installed controls, overlays, navigation, feedback, calendar and chart.
- **Artwork and Icons:** authored motifs, backgrounds and icons, with color and mono previews and copyable usage.
- **Foundations:** the approved palette, typography and six geometric building blocks.
- **Compositions:** six larger examples, including cards, metrics, carousel, reveal, resizable panes and authentication layout.
- **Assistant:** `/showcase?view=assistant` renders the actual assistant-ui components with explicitly illustrative conversation, reasoning, model, attachment, approval and error states.

## PycilAI

The robot button at the bottom right of the application shell opens PycilAI. The
panel occupies the right edge on desktop and the full viewport on mobile. Sign in
in live mode to send messages, choose a configured model/reasoning effort and reopen
saved conversations. AI allowance/reset dates come from `/me/usage`; history offers
confirmed deletion of owned conversations. Mock mode links to the showcase without making AI requests.

PycilAI uses the [existing AG-UI API](../../docs/backend/modules/assistant.md) through
the same bearer token and direct backend `/v1/*` routes as the rest of the app.
The server owns conversation history; the client sends only the new user message,
or an explicit approval resolution. Closing an active panel cancels the client run;
reopening fetches saved state without replaying an unknown turn.
If a remembered conversation returns 404, the panel clears that ID and opens a
new chat. Other failures retain the ID and offer retry.

Image attachments require a vision model and support PNG, JPEG and WebP. Each
message accepts up to four images, 10 MB per image, 8,000 text characters and a
15 MB complete encoded request. Library-changing tools show an approve/reject
panel, including after reopening the conversation. Reasoning disclosures render
only when the model supplies reasoning events; availability depends on the model.
Reasoning opens while streaming and text renders incrementally through the native
`useAgUiRuntime` / `HttpAgent` pipeline. The SSE response uses `no-transform` to avoid
compression buffering. Assistant streams connect directly to the backend; Next.js does not proxy them. The backend uses a 180-second SDK request timeout and has no deadline for the entire agent turn.
Image selection uses `ComposerPrimitive.AddAttachment` and the native image adapter;
the application adds model/MIME/size validation.

Reasoning and answer text share assistant-ui's native Markdown renderer with
remark math plugins and KaTeX. Both dollar and TeX delimiters are supported;
code remains literal. Bold text in reasoning is shown as a separate block because
provider summaries can concatenate section titles without line breaks. Display
formulas scroll horizontally only when needed, with vertical space for tall symbols.
Assistant content uses the available message width without an enclosing bubble around
reasoning/tool disclosures. Copy is shown only for messages containing answer text.

Owned styles and primitives are under `src/features/assistant/`. The focused
contract/browser suite is `pnpm exec playwright test assistant.test.ts --project=integration`.

The sidebar jumps to specimens; catalog search filters them. `Ctrl/⌘ K` or the header search button opens global navigation. The theme toggle persists via `bauhaus-theme`; the root layout applies the saved mode before hydration. Copy buttons offer selectable source when clipboard permissions are denied.

## Maintain the theme

The root [`DESIGN.md`](../../DESIGN.md) is the palette authority. The showcase does not redefine the product's learning-status semantics.

| Location | Responsibility |
| --- | --- |
| `src/app/globals.css` | Canonical palette literals, Tailwind theme, semantic color roles and global treatments |
| `src/components/ui/` | Official shadcn source; primitive behavior and component variants |
| `src/components/artwork/` | Authored paths, typed names and shared SVG renderers |
| `src/app/(public)/showcase/examples/` | Catalog examples, composition frames, source and copy affordances |
| `src/components/shell/` | Application shell and account controls |

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
