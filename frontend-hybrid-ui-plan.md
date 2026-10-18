# Hybrid Frontend, Public Content, and SEO Implementation Plan

Status: implemented and locally verified. No deployment is part of this change.

Date: 2026-10-19

## 1. Outcome and boundaries

Deliver one coherent learning product with a public website, publicly readable profiles and Published material, and an authenticated personal workspace.

The accepted design is:

- Landing, existing legal pages, and future blog content use the website layout and server-rendered public content. Building a blog is not part of this change.
- Personal learning and management under `/app/*` use client-driven data loading and the existing TanStack Query cache after the shell loads.
- Profiles and Published folders/decks under `/u/*` render public content on the server and hydrate their interactive views in the browser.
- All product browsing uses the same sidebar, mobile navigation, content frame, typography, and artwork. Signed-in users do not switch to a different-looking application when opening another author's material.
- Authentication changes available navigation, personal data, and actions. It does not decide whether public content can be read.
- The current Bauhaus identity remains authoritative. This is a consistency and behavior repair, not a visual rebrand.

Explicitly excluded: hosting migration, DNS, Cloudflare proxy changes, deployment topology, new monitoring infrastructure, assistant/backend job redesign, a new router/state framework, a new authorization framework, and speculative dependencies.

This file is the requested root-level execution plan. It records the decisions from this discussion; it does not silently replace unrelated plans or treat older documents as proof of current behavior.

## 2. Current evidence

The following findings come from the current workspace, not a claim that production has the identical revision:

| Finding | Current owner and consequence |
| --- | --- |
| Root tabs can remain on Overview after the URL changes | Personal and Published root pages pass a fixed `tab="overview"`; `LibraryView` changes the pathname with native history. |
| Direct Words entries can remain on Words | The dedicated `/words` pages pass a fixed `tab="words"`, while Overview entries use `LibraryNodePage` and `usePathname`. Tab ownership differs by entry point. |
| Public nodes use a separate, reduced renderer | `PublicNodeView` renders text/link lists instead of the folder, word-table, and preview compositions used by `LibraryView`. |
| Public routes already exist outside the private gate | `/u/*` is outside the `/app` layout calling `auth.protect()`. Public availability must be diagnosed through links, queries, and actions as well as layouts. |
| Public routes already render the existing AppShell | Keep that shared visual language; repair its guest behavior and ownership instead of introducing a separate public header-only product shell. |
| Profile loading is reused for nested nodes | `/u/loading.tsx` represents a profile but also covers descendant folder/deck routes. `PublicProfilePage` separately falls back to a text loading message. |
| Generic library loading assumes a grid and learning summary | It does not distinguish a deck preview, Words table, or a guest with no personal progress. |
| Landing authentication links are unconditional | `LandingHeader` always displays Login/Signup. |
| Discovery is missing header artwork | Its header currently contains title/description without the expected motif. |
| Public metadata is incomplete | Profile/node routes generate title and description, but do not define the complete canonical and social-card contract. |
| Public post-login destinations are already allowed | `safeReturnTo` currently accepts `/app` and `/u`. Reuse this validation rather than replacing it with unrestricted redirects. |

Relevant sources: [Library view](apps/web/src/features/library/library-page.client.tsx), [public node](apps/web/src/features/library/public-node.client.tsx), [library queries](apps/web/src/features/library/queries.ts), [public routes](apps/web/src/app/(product)/(workspace)/u), [auth flow](apps/web/src/features/auth/flow.ts), [product rules](PRODUCT.md), and [design rules](DESIGN.md).

## 3. Final navigation and rendering contract

### Route map

| Surface | URL | Access | Rendering and shell |
| --- | --- | --- | --- |
| Landing | `/` | Public | Server-rendered website, account-aware header |
| Legal | `/privacy`, `/terms` | Public | Server-rendered website layout |
| Blog | Future existing/planned blog routes | Public | Same website family; no new blog implementation here |
| Discovery | `/discovery` | Public | Existing catalog feature in the shared product shell |
| Dictionary | `/dictionary` | Public reads | Existing dictionary feature in the shared product shell; generation/saving require authentication |
| Profile | `/u/{identifier}` | Public | Server-rendered public identity and Published listing, then interactive browser queries |
| Published node | `/u/{identifier}/{nodeId}` | Public | Server-rendered Overview, shared folder/deck presentation |
| Published Words | `/u/{identifier}/{nodeId}/words` | Public | Server-rendered initial Words page, browser-driven filters/pagination |
| Personal workspace | `/app`, `/app/personal/*`, `/app/published/*`, `/app/settings` | Authenticated | Existing product shell, client-driven account/domain views |
| Focus learning | Existing `/app/learn`, `/app/flashcards` | Authenticated | Existing fullscreen focus layout |
| Authentication | Existing login/signup/callback routes | Public entry | Existing independent authentication layout |

`identifier` continues to support the existing handle or user-ID lookup. Prefer the current handle in canonical/share links when available; keep ID-based public links usable. Do not create a handle-history table or invent historical aliases.

Discovery and Dictionary move out of the private-only route subtree so guest sidebar links actually work. Update current internal links, action destinations, return-path validation, stories, fixtures, and tests together. Do not create two independently maintained implementations at the old and new paths. Decide any redirect for existing `/app/discovery` or `/app/dictionary` URLs from actual deployed-link usage before removing those entry points; a redirect, if needed, delegates to the single public route.

### Shared product shell

Keep the existing sidebar. Establish one shared workspace layout/provider owner for personal pages, `/u/*`, Discovery, and Dictionary, using Next route groups where needed. Preserve URL paths independently of filesystem grouping. Keep authentication and fullscreen learning outside that workspace frame.

The shared owner must preserve sidebar collapse state, account/query scope, assistant state for signed-in users, and the current scroll behavior during ordinary product navigation. Avoid mounting a new independent AppShell inside every public page. Do not replace Next navigation with a custom SPA router.

| State | Sidebar/account area | Main content | Assistant |
| --- | --- | --- | --- |
| Guest | Brand, Discovery, Dictionary, Login, Signup | Public identity and published material | Not mounted; no conversation or usage requests |
| Signed in | Home, My Library, Published, Discovery, Dictionary, current account | Same public content or personal workspace | Existing launcher and panel |
| Session resolving | Stable navigation/account dimensions with a quiet loading treatment | Public content remains readable | Wait for resolved authenticated state |
| Account task or account API failure | Explain/retry only the affected account action | Public content remains readable | Existing authenticated eligibility rules |

Opening foreign published material highlights Discovery; opening one's Published management area highlights Published. Never manufacture a Home, personal library, progress band, or disabled private-menu inventory for a guest.

### Website account header

- Guest: Login and Signup.
- Signed in: Open app plus the existing account/avatar interaction adapted for this location.
- Resolving: reserve the account-control area; avoid a flash of Login followed by an avatar.
- Use the existing Clerk/session source. Do not make the entire landing page wait for learning data or add a second identity system/provider.
- Keep legal and website navigation correct outside the landing page; section anchors must target the landing route when used elsewhere.

## 4. Permissions and public/private data separation

| Capability | Guest | Signed-in visitor | Owner |
| --- | --- | --- | --- |
| Read profile/bio/Published tree | Yes | Yes | Yes |
| Read published folder/deck and Words | Yes | Yes | Yes |
| Search/sort/paginate public material | Supported public options | Supported public options | Supported public options |
| Flip/browse inline flashcard preview | Yes; no learning submission | Yes | Yes |
| Share/copy a public link | Yes | Yes | Yes |
| Study, save reference, generate vocabulary | Login required | Existing authorized behavior | Existing authorized behavior |
| See personal learning state | No | Own learning state only | Own learning state only |
| Edit/delete/move/publish/unpublish | No | No for foreign content | Existing ownership and publication rules |

Backend authorization remains authoritative. Hiding a button is not access control. Public reads must omit personal progress, private source memberships, account preferences, email addresses, and private ancestors.

Anonymous requests must not ask for authenticated-only includes or filters. Hide personal-state filters such as Due and Last reviewed when no personal state is available. Unknown personal state must not appear as zero progress, New, or unavailable public content.

Public SSR reads use an anonymous public-data path even if the browser has a session. Account and personal learning enrichment must not block that public content or enter shared public cache/metadata/OG output. Reuse existing API endpoints and permission rules; change backend contracts only for a demonstrated missing requirement.

## 5. Repairs and implementation detail

### A. Make URL and tab state agree

- Give Overview/Words one URL-aware owner across root pages, normal nodes, references, and public routes.
- Remove fixed tab props where native history can change the active pathname without rerunning the server page.
- Reuse existing Next pathname/search-param hooks and URL helpers. Do not add a second independent tab state.
- Preserve root selection, node identity, creation dialogs, appropriate filters, and cursor reset behavior when changing scope/tab.
- Support direct entry, refresh, click, keyboard activation, and Back/Forward equally.
- Folder Words continues to use the backend's scoped sense behavior, including deduplication/reference semantics. Do not implement a frontend tree crawler to collect words.

### B. Unify node presentation

Refactor existing library components at the point where public and personal views diverge:

- Shared header: breadcrumb, name, description, author, publication/reference indicators, deterministic motif, and permitted actions.
- Shared folder Overview: Subfolders/Decks sections, cards/list toggle, correct reference artwork, search, pagination, and context-appropriate empty states.
- Shared deck Overview: the existing controlled Flashcard presentation, browse/flip controls, and deck metadata.
- Shared Words: lexical rows/details, definitions, examples, accessible controls, sorting/search, and pagination.
- Optional personal enrichment: the viewer's learning columns, summary, and Study actions, without changing the core content layout.
- Owner actions: preserve editing, sense deltas, move/copy, deletion, publication confirmation, and destination selection.

Keep query/mutation ownership in the feature containers/hooks. Presentation receives the data and actions it needs. Avoid a generic renderer registry, permission framework, or a large set of unrelated boolean flags.

Do not merely pass a null profile into today's `LibraryView`: it currently assumes authenticated account/progress dependencies. Reuse the real presentations while making those dependencies explicit and optional where the public contract requires it.

Replace the reduced public text/link renderer after parity is covered. Remove superseded markup, queries, props, imports, and fixtures rather than maintaining a legacy public mode.

### C. Repair profile and published navigation

- Profile remains a public identity header plus the author's browsable Published tree, using the same library listing presentation.
- Owner profile editing remains available under the existing identity/ownership rules; visitors never receive owner mutation controls.
- Owned Published management and public Published viewing use the same folder/deck compositions.
- Public browsing keeps breadcrumbs and child links on public routes, including when the viewer owns that material. Management links are intentional actions, not accidental breadcrumb destinations.
- Share always uses the public canonical destination; never copy `/app/published/*` as a share link.
- Personal nodes retain private navigation and do not gain an anonymous share operation.
- A reference keeps its own label/placement/author context. Opening its source uses the target's actual owner and ID; do not place a foreign target ID beneath the wrong author URL.
- Unavailable references preserve the existing safe unavailable state without leaking private target names or ancestors.
- Public word-detail links use the guest-accessible dictionary route, preserving the selected word/sense where supported.
- Retry and not-found treatments distinguish a failed request from a missing/unpublished object.

### D. Complete login-to-learn/save flows

- Reading and previewing never trigger forced authentication.
- Study and Save are visible, meaningful actions for guests; activating them starts the existing authentication flow.
- Preserve the public document/tab and intended action across sign-in, sign-up, Google callback, and account-task continuation.
- Extend the existing safe return-path validator only for the selected public product routes. Continue rejecting external/protocol-relative URLs and malformed destinations.
- Resume Study through the existing preparation flow. Resume Save by opening the destination/confirmation UI, not by silently writing to a guessed location.
- Consume a resumed action once; reload/Back must not repeat a mutation. Use existing route/state mechanisms rather than a new persisted job or intent service.
- Cancellation returns to readable public content. If the material became unavailable during login, show that state and perform no mutation.

### E. Make loading and errors match the page

- Profile: identity header skeleton plus Published listing skeleton.
- Folder Overview: library header plus folder listing skeleton.
- Deck Overview: library header plus Flashcard and metadata skeleton.
- Words: header, appropriate toolbar, and word-table skeleton.
- Preserve the shell outside route loading; retain known data while unrelated background refetches run.
- No guest learning-summary skeleton, nonexistent create controls, profile skeleton on a deck, or text-only fallback competing with a different route skeleton.
- Account resolution/error must not replace already available public content with a whole-page loading/error state.
- Keep readable empty states for empty folders/decks and profiles with no publications. They remain valid public pages even when excluded from indexing.
- Add meaningful status announcements, keyboard focus behavior, Retry/Back actions, and reduced-motion support using current primitives.

### F. Restore Discovery consistency

- Add the top-right motif using the existing artwork catalog and header conventions.
- Match the title/motif grid to the rest of the product, with appropriate clipping and mobile reduction.
- Update its skeleton to the actual header/list composition.
- Keep working search/type filters, author attribution, cards, pagination, and public node destinations.

## 6. SEO and social preview contract

### Server HTML and metadata

- Public initial HTML contains the actual profile identity, folder child links, or the first page of deck Words/preview text. A skeleton plus serialized query data alone is insufficient.
- Hydration reuses matching TanStack data and query keys, avoiding an immediate duplicate fetch caused by mismatched scope/options.
- Public pagination uses real link destinations that work without executing a click handler; interactive browser transitions remain available.
- Do not fetch an unbounded library to build HTML, counts, metadata, or images. Preserve server page limits and cancellation/timeouts.
- Generate title, description, canonical URL, Open Graph, and Twitter card metadata from the same permitted public object used by the page.
- Reuse public fetch memoization for metadata/page work. Do not fetch private account details to generate public metadata.
- Metadata is present for supported social crawlers in the server response, using the installed Next version's documented behavior.
- Set absolute production URLs from one existing/appropriate site-origin source. Preview/test deployments must not become production canonicals or searchable copies.

### Canonical and index policy

| Surface | Policy |
| --- | --- |
| Landing and actual published blog pages | Indexable |
| Non-empty public profiles and readable non-empty published folder/deck Overview | Indexable, self-canonical |
| Empty profiles/material | Still readable; `noindex` |
| Public Words tab | Keep the functional direct URL; initially `noindex, follow`, excluded from sitemap to avoid competing with the document Overview |
| Search/filter results, cursor variants, Dictionary query UI | `noindex`; do not enumerate combinations in sitemap |
| Private workspace/auth/focus/settings | Not indexable; private routes still enforce real authentication |
| Missing/deleted/unpublished material | Appropriate public not-found response, not an indexable success/error placeholder |

Canonicalize genuinely duplicate identifier/tracking variants to the preferred public URL. Do not point materially different paginated content at page one as if identical. Do not add a permanent redirect for an old handle unless existing identity data can resolve it correctly.

Add sitemap/robots using native Next conventions. Include eligible canonical profiles/material with bounded enumeration, and use real content timestamps for `lastModified`. Do not use sitemap generation to recursively crawl arbitrary content or load every sense. If a small public listing contract is missing, add only the bounded read required and verify privacy against the backend's owning module.

`robots.txt` is crawl guidance, not authorization or a substitute for `noindex`. Do not block a public variant from crawling and then depend on its unseen `noindex` for removal. Do not claim indexing or search ranking is guaranteed.

### Preview images

- Generate public PNG social cards at 1200 x 630 with native Next image/metadata support.
- Reuse the existing Pycil SVG logo/mark, fonts, tokens, and deterministic artwork; no AI-generated asset, external screenshot service, or new image framework.
- Profile card: public display name/handle and bounded bio text.
- Folder/deck card: title, author, material type, and restrained branded motif.
- Wrap/truncate long content predictably. Treat user text as text; no raw HTML or arbitrary remote asset fetching.
- Counts are optional and may appear only when already available through a safe bounded public read. Do not invent counts or run expensive private progress aggregation for a social card.
- Image endpoints work anonymously and recheck publication/readability. Do not expose deleted/private material through a cached image route.
- Any public-data cache has a bounded freshness/revalidation policy and invalidates on publication changes; never cache personalized HTML as public.
- External services can retain previews after unpublish. Document this limit; do not promise remote cache erasure.

Current SEO work starts from existing title/description support. It does not require a separate SEO service or infrastructure rollout.

References: [Next metadata and OG images](https://nextjs.org/docs/app/getting-started/metadata-and-og-images), [Google canonical URLs](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls), [Google robots metadata](https://developers.google.com/search/docs/crawling-indexing/robots-meta-tag).

## 7. Expected change owners

These are existing owners to inspect/change as needed, not a requirement to edit every listed file or create a new layer.

| Area | Existing owners |
| --- | --- |
| Route layout and public SSR | `apps/web/src/app/(product)/(workspace)/u/**`, `apps/web/src/app/(protected)/app/**`, root layout, public Discovery/Dictionary route entries |
| Shell and session | `components/shell/{app-shell,app-shell-frame.client,shell-rail.client,mobile-app-bar.client,navigation,account-menu.client}`, `lib/auth/{product-provider,session-provider.client,account}` |
| Library presentation and actions | `features/library/{library-page.client,public-node.client,library-header.client,library-folder.client,library-words.client,library-flashcard-preview.client,library-node-actions.client,public-collection-actions.client,library-skeletons}` |
| Public/personal queries and links | `features/library/{model,queries,public-queries,public-server,use-library.client,invalidate}`, `lib/api/services/{contracts,http,mock}` and existing mock fixtures |
| Profile and guest dictionary | `features/account/public-profile-page.client`, `features/vocabulary/dictionary-page.client` and their existing queries/details |
| Authentication continuation | `features/auth/{flow,clerk-form.client,auth-callback.client}`, `app/(auth)/auth/complete/route.ts` |
| Landing and Discovery | `components/landing/landing-header`, `features/library/{discovery-page.client,discovery-skeletons}` |
| SEO | Root/page metadata; new native `robots`, `sitemap`, and route-scoped OG image entries only where required |
| Text and documentation | Existing locale messages, `apps/web/README.md`, owning sections of `PRODUCT.md` and `DESIGN.md` |
| Tests | Existing frontend unit/service/browser suites and root `e2e/` public/library/profile/navigation/rendering journeys |

Before implementation, refresh CodeGraph/source for these owners and inspect existing pending changes. Preserve concurrent work and unrelated backend/infra edits. Do not use a broad checkout/reset or turn this repair into a repo-wide cleanup.

## 8. Execution order and acceptance gates

| Step | Work | Depends on | Acceptance gate |
| --- | --- | --- | --- |
| 1 | Reproduce failures and capture incumbent desktop/mobile views | Current workspace | Confirm root/direct Words failures and public/personal rendering gaps; distinguish local from deployed behavior |
| 2 | Repair common shell/provider ownership, guest routes, and URL/tab state | Step 1 | Private gate remains intact; guests browse public pages; signed-in navigation keeps the product frame; all tab entry paths agree |
| 3 | Unify folder/deck/reference/profile presentation and data dependencies | Step 2 | Public/personal visual parity with correct per-viewer actions; public reads make no private requests |
| 4 | Complete login continuation, landing account controls, loading/error states, and Discovery motif | Steps 2-3 | Guest-to-signed-in action works once; account failures do not block public reading; loading matches each page |
| 5 | Add canonical/robots/sitemap/OG and verify server HTML | Steps 2-4 | Anonymous HTML and image requests satisfy the public SEO contract; unpublished/private data is excluded |
| 6 | Run focused/full affected checks, bounded visual review, and update owning docs | Steps 1-5 | Tests pass, desktop/mobile and light/dark inspected, actual behavior documented, dead duplicate code removed |

Each step is unfinished until its callers, fixtures, mock/live adapters, routes, and tests agree. Do not mark a phase complete solely because a mock screenshot looks correct.

## 9. Validation matrix

### Navigation and interaction

The checklist records local verification against source and automated coverage. External-provider and external-preview checks remain explicitly separate.

- [x] Personal root and owned Published root: Overview -> Words -> Overview.
- [x] Normal folder/deck and folder/deck reference: same tab sequence.
- [x] Direct `/words` entry, refresh, keyboard navigation, and Back/Forward.
- [x] Guest opens public profile, nested folder, deck, and reference without a login redirect.
- [x] Guest browses folder card/list mode, scoped search, Words sort/search, pagination, and preview.
- [x] Public Words and dictionary links do not enter a protected route just to read.
- [x] Signed-in user opens own/foreign published nodes without a shell change or unintended assistant reset.
- [x] Sidebar current item, collapse state, mobile menu, skip link, and existing scroll restoration remain correct.
- [x] Save/Study login continuation works with real Clerk password sign-in; refresh does not repeat the action.
- [ ] Manually repeat the existing Google sign-in continuation on the deployed revision; its shared return-path handling is unchanged.
- [x] Landing uses Clerk session state and UserButton for authenticated account controls; guest links remain covered by browser tests.

### Permissions and state

- [x] Guest receives no private includes, learning/progress requests, assistant requests, or owner controls.
- [x] Visitor sees their own progress only; owner actions remain correctly gated by backend permissions.
- [x] Public content survives delayed Clerk resolution and failed account/profile enrichment.
- [x] Empty, loading, API failure, not-found, unavailable reference, and unpublish-after-open states are distinct.
- [x] Session switch/sign-out clears account-scoped TanStack data without exposing the previous user's state.
- [x] Existing edit, publication confirmation, sense mutation, save-reference, Study preparation, and review behavior remain intact.

### SEO and presentation

- [x] Anonymous HTTP response contains real public identity/content and crawlable child/pagination links.
- [x] Correct title/description/canonical/OG/Twitter metadata on profile/folder/deck responses.
- [x] Social-card image returns PNG with the expected dimensions without cookies/authentication.
- [ ] Long titles, empty bio, Unicode, missing optional identity artwork, light/dark UI, desktop, and mobile remain legible.
- [x] Sitemap contains only eligible canonical published objects; private/unpublished/deleted objects are absent.
- [x] Unpublished content returns 404 from both HTML and OG image URLs (real API E2E).
- [ ] Verify with normal and representative social-crawler user agents; actual external preview checks are reported separately from local metadata assertions.

### Test ownership and commands

Start with the narrowest existing suite for each changed behavior. Extend existing tests rather than duplicating the product journey at every layer.

- Unit: URL/tab helpers, safe return/action parsing, capability decisions if extracted, canonical/index decisions.
- Service integration: anonymous versus authenticated query parameters, supported filters, parsing, and mock/live contract parity.
- Browser integration: the real shell, tab switching/history, profile/library compositions, account-aware landing, and accessible loading/actions.
- Root E2E: anonymous public reading, real authenticated continuation, ownership, publication/unpublication, and server HTML/metadata behavior using disposable infrastructure.
- Backend tests only when a backend contract actually changes; then run the affected real library/account integration tests.

Commands from repository root (select affected files first):

```sh
pnpm --dir apps/web exec vitest run tests/unit/auth-flow.test.ts tests/unit/library-contracts.test.ts --project unit
pnpm --dir apps/web exec playwright test library-navigation.test.ts app-shell.test.ts profile-settings.test.ts landing.test.ts --project=integration
pnpm --dir apps/web run typecheck
pnpm --dir apps/web run lint
pnpm --dir apps/web run build
pnpm --dir e2e exec playwright test tests/discovery/public-library.test.ts tests/account/profile.test.ts tests/platform/navigation.test.ts tests/platform/server-rendering.test.ts --project=default
```

Update command selections if tests are moved for a real ownership reason. Include additional affected library/auth/service tests, then run the full frontend suite when shared presentation/session changes are complete. Missing E2E credentials or external preview access must be reported as missing coverage, not a pass.

Perform one batched visual inspection across desktop/mobile and relevant themes, fix the observed issues together, and perform one confirmation pass. Check for an existing project server before starting one, track owned processes/ports, and stop only those started for this work.

## 10. Documentation, release boundary, and risks

- Update `apps/web/README.md` for the actual rendering, public route, authentication-continuation, and cache behavior once implemented.
- Update the owning `DESIGN.md` shell/profile/library/loading sections. Its older `/app/u/...` route text is stale; replace it with verified routes, not another contradictory appendix.
- Update only affected `PRODUCT.md` public-reading/navigation/indexability decisions. Preserve vocabulary, publication, reference, and learning semantics.
- Update this plan's completion state using verification evidence. Do not rewrite unrelated DevOps/course documentation merely to record phase progress.
- No production deployment or infra migration is implied by completing this file. Validate the application changes first, then use the existing delivery process when deployment is requested.
- Rollback is the prior frontend release through the existing release mechanism; this plan introduces no destructive data migration. Coordinate any narrowly required API addition so the current frontend continues to work during rollout.
- Main risks: route/layout regrouping can remount providers; shared components can accidentally issue private queries for guests; cached public HTML/images can retain unpublished content; handle aliases and social-platform caches have limits. Verify these explicitly rather than adding speculative infrastructure.
- Completion means the accepted guest/signed-in/owner journeys, all original reported UI defects, and the SEO/share contract are verified. Hosting/latency tuning and the separate assistant investigation remain separate work.

## 11. Implementation and verification record

Implemented the shared product route group/provider, guest navigation, public/private component parity, URL-owned tabs, matching skeletons, independent personal enrichment, action continuation, landing account controls, and native metadata/social image routes. Removed the duplicate public contents/meanings API wrappers and unused server author helper. Public route-level streaming fallbacks were removed after a no-JavaScript test demonstrated they hid the readable page; client query loading remains page-specific.

Verification completed so far:

- Frontend: 150 unit/service/asset assertions across 33 Vitest files; TypeScript and lint passed (existing lint warnings remain).
- Browser: the full 102-test suite passed 101 tests and exposed an early sidebar click before hydration; the collapse control now waits for hydration. All 23 affected shell/artwork tests passed after that fix, including the clock test and disabled pre-hydration control assertion. All 34 previously affected shell/artwork/Home/library-action tests also passed. This record does not describe the earlier full run as green.
- Live E2E against disposable PostgreSQL/Redis/API and Clerk test identities: all seven public-library/server-rendering journeys, plus two real guest Save/Study sign-in continuations, passed. Production frontend builds are part of those runs.
- Accumulated backend changes: 336 unit tests and 243 integration tests passed; one integration test remains explicitly skipped by the existing suite. Ruff passed.
- Accumulated VPS tooling: three controller/smoke tests and shell syntax checks passed.
- Desktop public deck/profile/Discovery and mobile dark Words views inspected; no horizontal overflow at 1440/390 px. Existing browser theme/keyboard checks cover shared controls.
- Staged changes scanned with Gitleaks: no secrets found.
- Unpublish-after-open E2E: both public HTML and OG image return 404 after the owner moves the deck back to Personal.

No claim is made about Google re-verification, external social-platform caches/previews, production deployment, or resolving the separate production latency investigation. The sitemap deliberately seeds at most 50 eligible discovery entries; deeper items remain linked from public pages.


Release validation on 19 October 2026 found stale E2E accessible names after the
shared library UI change, a resize assertion racing the asynchronous background
layout, a search-metric assertion racing synchronization completion, and missing
backup/observability inputs in the Compose CI check. These checks now follow the
actual public/private controls and wait for the observed operation to finish;
no product assertions were removed. The PostgreSQL bootstrap user finding is
limited to its Dockerfile in the shared Trivy policy; live PostgreSQL runs as
`postgres`, and the backup utility uses UID 999.

The complete backend run passed 582 tests with one existing skip. The local E2E
run passed 83 of 84 before the final card-link locator correction; both publication
journeys passed in the targeted rerun. The artwork resize test passed five repeated
runs, and local/VPS Compose, Caddy, and three deployment checks passed. The full
frontend CI job passed. Production promotion still waits for the final revision's
CI and verified backend image publication.
