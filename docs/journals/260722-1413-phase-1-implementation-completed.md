# Technical Journal: Phase 1 Core Content Management Implementation Completed

- **Date**: 2026-07-22
- **Topic**: Phase 1 Core Content Management (Page `/library` & Page `/decks/[id]`)

## What Was Implemented
1. **BFF API Routes & Types**:
   - Added TypeScript Node/Sense DTOs to `apps/web/lib/api/types.ts`.
   - Added Node & Deck API methods to `apps/web/lib/api/client.ts`.
   - Created BFF Next.js route handlers under `apps/web/app/api/nodes/` and `apps/web/app/api/decks/`.
   - Created custom React Query hooks in `apps/web/lib/query/nodes.ts` and `apps/web/lib/query/decks.ts`.

2. **Page `/library` (Folder & Deck Tree)**:
   - Added `BreadcrumbNav` component supporting multi-level breadcrumb history.
   - Added `NodeCard` component displaying Folder / Deck / Reference Deck metadata, visibility badges, and dropdown action menu.
   - Created modal dialogs: `CreateNodeDialog`, `EditNodeDialog`, `MoveNodeDialog`, `DeleteNodeDialog`.
   - Assembled `/library` page supporting search filtering, empty states, and optimistic UI updates.

3. **Page `/decks/[id]` (Deck Details & Word List)**:
   - Created `MasteryBadge` mapping 0-100% FSRS score to Level 1-11 badges.
   - Created `SenseItemCard` displaying definition, POS, CEFR level, collapsible examples, and word removal.
   - Created `DeckHeader` displaying metadata, overall mastery, and CTAs ("Học ngay" -> `/study?deckId=[id]` & "Thêm từ mới" -> `/search?deckId=[id]`).
   - Assembled `/decks/[id]` page with loading skeletons and empty state support.

4. **Verification**:
   - Verified `npm run typecheck` passes with 0 errors.
   - Verified `npm run build` compiles production build successfully in Next.js Turbopack.

## Status
- Plan `plans/260722-1408-phase-1-core-content-management/plan.md`: 100% Completed (4/4 phases).
