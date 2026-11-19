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
server authentication and preference completion also require the matching `CLERK_SECRET_KEY`. Clerk issues the
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

The frontend is hybrid. Landing and legal pages use the public website layout.
`/u/[identifier]` and nested published folders/decks render anonymous public data
on the server and hydrate the matching TanStack Query cache. Personal `/app/*`
views load account and domain data in the browser. Fresh browser queries are
reused for 60 seconds across ordinary product navigation.

Personal pages, public profiles/material, `/discovery`, and `/dictionary` share
one product shell and provider. Guests see only public navigation and authentication
actions; PycilAI mounts after the account is ready. Signing out keeps the current
public page; private `/app/*` pages return to `/discovery`. `/app/*` remains protected,
with learning routes using their existing fullscreen layout. Previously deployed
`/app/discovery` and `/app/dictionary` links redirect to the public routes.

Public server reads never attach a bearer token or load personal learning data.
Account/progress enrichment loads independently in the browser. Public and personal
views reuse folder, flashcard, and Words presentations; guest views omit learning
filters, private sources, and owner actions. Save/Study sends guests through the
existing login flow with a validated return path. Save then opens destination
selection; Study opens preparation. The continuation is consumed before acting.

Filters, cursors, selection and mutations call Pycil directly from the browser;
Next.js has no CRUD forwarding endpoints or Server Actions. Native history owns
Overview/Words state, including direct URLs, reload and Back/Forward. Pagination
also has real link destinations for anonymous server rendering.

The browser cache is scoped to the active Clerk session and cleared on a session
change. Public query keys omit the viewer identity; account and learning queries
remain scoped. Public reading does not wait for Clerk or account enrichment.

The `pycil-theme` cookie owns light/dark rendering. NextIntl owns locale messages;
the locale cookie, Accept-Language and English fallback determine server rendering.
Successful settings saves and `/auth/complete` synchronize the saved locale cookie.
The completion route writes Next.js-owned preferences and redirects; it is not a
backend API proxy. Personal and own Published material use `/app/personal` and
`/app/published`; public profiles and collections use `/u/[identifier]`.

Domain views live in `src/features/{home,account,auth,library,vocabulary,study,assistant}`.
Shared controls, artwork and shell live in `src/components`. Shared HTTP, identity,
query and preference boundaries live in `src/lib/{api,auth,query,preferences}`.

## Public metadata and sharing

Set `NEXT_PUBLIC_SITE_URL` to the canonical frontend origin (production defaults to
`https://pycil.qninhdt.com`). Public profiles and non-empty published Overview pages
have canonical, Open Graph and Twitter metadata. Words, search/cursor variants,
empty public collections, auth and private pages are not indexable. Development,
mock mode and Vercel preview builds are not indexable.

Native `robots.txt` and `sitemap.xml` expose crawl guidance and a bounded seed of
the latest 50 eligible Discovery entries, with at most five concurrent validations.
Deeper content remains reachable through public links; the sitemap is not an
exhaustive export of every published node. Public social-image routes use bundled
logo/fonts, return 1200 × 630 PNG, recheck visibility and send `private, no-store`.
Page metadata and social images share the public resource title and description,
using the author's name when no profile bio or collection description is provided.
Public HTML is also read without a shared Next data cache. External search/social
services can retain their own previews after unpublishing.

## Landing page

`/` is the public Bauhaus landing page; `/app` opens the learning application.
The landing page's English learning worksheet lets visitors choose a meaning of
“bank” and try its contextual question. It is a labeled local example: it does
not save Library changes or submit learning progress. Signup and sign-in actions
use the existing `/signup` and `/login` routes. Signed-in visitors see Open app
and their Clerk account menu instead; the rest of the landing page remains server-rendered.

`/privacy` and `/terms` are public, server-rendered legal pages linked from the
landing footer. Keep their data-handling descriptions aligned with the deployed
providers and retention behavior. Google OAuth Branding and Clerk production
must reference these same URLs; domain ownership is verified separately through
Google Search Console using the OAuth project's owner account.

The page uses Tailwind, shared palette tokens, artwork and shadcn buttons. Static
content lives in `src/components/landing/landing-page.tsx`; the interactive example
lives in `learning-map.client.tsx`. Run `pnpm exec playwright test landing.test.ts --project=integration`
for interaction, navigation, responsive and theme checks.

## Live integration and E2E

Home, account/settings, Library, Dictionary, study/flashcards and PycilAI use the
live service adapter. Discovery reads the public catalog. Library edits use atomic
sense deltas and metadata patches; move, copy, publish/unpublish and saved references
use the [backend Library contracts](../api/pycil/library/).
Public creation/publication requires explicit confirmation. Viewing flashcards does
not submit reviews. Accepted reviews invalidate progress/reporting queries.

Practice, Learn new and Review enter `/app/learn` directly from Home or any
Library scope. Signed-out visitors can read Published folders/decks and public
meanings through the same canonical links, without personal learning details.
Learning, practice and flashcard exits from the Library root return Home; specific
deck/folder sessions return to their source. Preparation runs inside focus mode;
failures use an accessible popup
with Retry and Back to My Library. Leaving preparation cancels the browser request.
Storage failures stop advancement and show recovery instead of silently losing answers.

Use **Create reference** in a folder/deck's menu, after **Copy**, to name a live
link and choose its destination. This is also available for other users' Published
material. A Published reference links to its original folder/deck. Private sources
can be saved in Personal; Published sources can also be saved in Published with
explicit confirmation.

Product browser E2E lives in the [`tests/e2e`](../../tests/e2e/README.md)
package. From the repository root:

```sh
pnpm --dir tests/e2e test
pnpm --dir tests/e2e test:live
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

PycilAI uses the [AG-UI API](../api/pycil/assistant/api.py) through
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
