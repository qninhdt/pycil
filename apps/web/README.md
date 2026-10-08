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
`NEXT_PUBLIC_DATA_MODE=live`. The frontend uses `@clerk/react` in the browser;
it needs no Clerk secret key or authentication middleware. Clerk issues the
session token, which the frontend sends as a bearer token through `/api/v1/*`.
Next.js only forwards these requests to `PYCIL_API_URL` (default
`http://127.0.0.1:8000`); the API verifies the token using Clerk's public JWKS.
The frontend loads its own environment files and does not load the root `.env`.

```sh
pnpm run build    # TypeScript checks + production build
pnpm run lint     # Oxlint
pnpm exec playwright install chromium
pnpm run test
```

The existing mock UI suite starts a Next.js server using the port in `playwright.config.ts`. For a preinstalled Chromium, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable. To retain the visual matrix outside ignored `test-results/`, set `SHOWCASE_SCREENSHOT_DIR`.

## Live integration and E2E

Home, account/settings, Library, Dictionary, study/flashcards and PycilAI use the
live service adapter. Discovery reads the public catalog. Library edits use atomic
sense deltas and metadata patches; move, copy, publish/unpublish and saved references
use the [backend Library contracts](../../docs/backend/modules/library.md).
Public creation/publication requires explicit confirmation. Viewing flashcards does
not submit reviews. Accepted reviews invalidate progress/reporting queries.

Run the managed full-stack profile from the repository root after starting the
frontend in live mode on port 3000:

```sh
RUN_WEB_E2E=1 python scripts/test_api.py tests/system/test_web_e2e.py -s -q --tb=short
```

The runner starts the real API on port 8000, owns disposable PostgreSQL/Redis,
prepares native lexical/question data, and runs `pnpm run test:e2e` against the
existing Next server. It refuses an occupied API port and never changes FE dotenv
files or starts another frontend. The runner reads the matching development Clerk
configuration from the root `.env` (`E2E_CLERK_ENV_FILE` can select a runner-only
file). A Clerk secret is required only by the runner to provision/delete its own
temporary test users and obtain the official bot-protection testing token. Browser
authentication uses the actual custom forms, email verification/client-trust
challenges and Clerk session JWTs verified by the API. There is no auth mock or
locally signed session token.

The suite covers authentication, profile/settings, Home/reporting, Library writes,
publication/references/Discovery, source pagination, Dictionary/worker generation,
all seven question types, typed grading, FSRS reviews/idempotent replay, flashcards,
Assistant SSE/history/approval/deletion/usage, account isolation and mobile completion.
Only external inference is deterministic in the default profile; API, native worker,
validation, domain services, PostgreSQL, Redis and checkpoint history remain real.
Transport fault tests delay or abort requests, including after real server acceptance.
Test-only Library limits make quota boundaries inexpensive to exercise; production
policy is unchanged. Test-owned nodes and Clerk users are cleaned by exact ID;
the managed store runner removes its containers, network and volumes.

Use `E2E_GREP='pattern'` with the managed command to run a focused group. Google OAuth
completion requires dedicated `E2E_GOOGLE_EMAIL` / `E2E_GOOGLE_PASSWORD` runner
credentials. Authenticator MFA tests enroll their own user and explicitly skip if
Clerk reports that the feature is disabled. Account continuation requires an
instance configured with the corresponding pending task; it is not inferred from
successful ordinary login.

The separate external-provider smoke profile uses the actual configured inference
and decision services for generation, typed grading and Assistant streaming:

```sh
RUN_WEB_E2E=1 E2E_PROVIDER_PROFILE=live python scripts/test_api.py tests/system/test_web_e2e.py -s -q --tb=short
```

It requires `INFERENCE_API_KEY`, `INFERENCE_BASE_URL`, `LEXI_DECISION_API_KEY` and
`LEXI_DECISION_BASE_URL` in the runner environment/file. It fails before creating
users if configuration is missing. Legacy provider variable names are not silently
translated. This profile invokes paid services and is separate from routine E2E.

HTML reports and failure screenshots use ignored `e2e-report/` and `e2e-results/`.
Network tracing is disabled because it records credentials/bearer tokens. Treat test
artifacts as private. Execution evidence and external limitations are recorded in
the [English E2E plan](../../tmp/frontend-backend-e2e-plan.md); collection alone is
not evidence of successful execution.

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
the same bearer-token and `/api/v1/*` forwarding route as the rest of the app.
The server owns conversation history; the client sends only the new user message,
or an explicit approval resolution. Closing an active panel cancels the client run;
reopening fetches saved state without replaying an unknown turn.

Image attachments require a vision model and support PNG, JPEG and WebP. Each
message accepts up to four images, 10 MB per image, 8,000 text characters and a
15 MB complete encoded request. Library-changing tools show an approve/reject
panel, including after reopening the conversation. Reasoning disclosures render
only when the model supplies reasoning events; availability depends on the model.
Reasoning opens while streaming and text renders incrementally through the native
`useAgUiRuntime` / `HttpAgent` pipeline. The SSE response uses `no-transform` to avoid
compression buffering. Next uses a 210-second proxy inactivity timeout; the backend
uses a 180-second SDK request timeout and has no deadline for the entire agent turn.
Image selection uses `ComposerPrimitive.AddAttachment` and the native image adapter;
the application adds model/MIME/size validation.

Reasoning and answer text share assistant-ui's native Markdown renderer with
remark math plugins and KaTeX. Both dollar and TeX delimiters are supported;
code remains literal. Bold text in reasoning is shown as a separate block because
provider summaries can concatenate section titles without line breaks. Display
formulas scroll horizontally only when needed, with vertical space for tall symbols.
Assistant content uses the available message width without an enclosing bubble around
reasoning/tool disclosures. Copy is shown only for messages containing answer text.

Owned styles and primitives are under `src/components/assistant-ui/`. The focused
contract/browser suite is `pnpm exec playwright test tests/assistant.spec.ts`.

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
