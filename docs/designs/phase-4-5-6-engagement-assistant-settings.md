# Design Document: Phase 4, 5 & 6 — Engagement, AI Assistant & Account Management

**Date:** 2026-07-22
**Status:** Approved
**Scope:** `Page /dashboard`, `Page /assistant`, `Page /settings` + Backend Wiring (`apps/api` and `apps/web`)

---

## 1. Executive Summary & Requirements

This feature package implements the final core user-facing web pages and backend integrations for Pycil:

1. **`Page /dashboard` (Priority #5 - Engagement & Overview)**:
   * Provides learners with daily study motivation and retention visibility.
   * Total learned/mastered words count & words due today.
   * 7-day FSRS review workload forecast chart (`Recharts`).
   * Quick action card to immediately resume the latest study session.

2. **`Page /assistant` (Priority #6 - AI Chatbot & HITL)**:
   * Interactive AI assistant powered by Pycil's SSE backend (`/v1/assistant`).
   * Real-time stream parsing (`token`, `action`, `done`, `error`).
   * Human-in-the-loop (HITL) inline confirmation cards for sensitive actions (e.g., Deleting or Moving Folders/Decks) requiring explicit user Approval/Rejection (`POST /v1/assistant/threads/{id}/actions/{action_id}/confirm`).

3. **`Page /settings` (Priority #7 - Account Management)**:
   * User profile overview (Name, Email, Account metadata).
   * One-click data export (`GET /v1/me/export`) as a JSON download.
   * Account deletion (`DELETE /v1/me`) with strict double-confirmation modal demanding text confirmation `"DELETE"` and active session revocation.

---

## 2. System Architecture & Endpoints

### 2.1 Backend Endpoints (`apps/api/pycil`)

1. **Dashboard Endpoint (New)**:
   * `GET /v1/learning/dashboard` (Authenticated)
   * **Location**: `apps/api/pycil/learning/router.py`
   * **Logic**: Queries `user_sense_stats` for total learned senses (`mastery > 0`), due senses (`next_review_date <= NOW()`), computes a 7-day due date distribution histogram, and resolves the user's most recent active deck/session.
   * **DTO (`DashboardStatsRead`)**:
     ```python
     class FSRSForecastDay(BaseModel):
         date: str  # YYYY-MM-DD
         due_count: int

     class RecentSessionInfo(BaseModel):
         node_id: UUID
         deck_title: str
         remaining_count: int

     class DashboardStatsRead(BaseModel):
         total_learned_words: int
         due_today_count: int
         mastery_percentage: float
         fsrs_forecast: list[FSRSForecastDay]
         recent_session: RecentSessionInfo | None
     ```

2. **Assistant Endpoints (Existing)**:
   * `POST /v1/assistant/threads` & `GET /v1/assistant/threads`
   * `POST /v1/assistant/threads/{thread_id}/messages` (SSE Stream)
   * `POST /v1/assistant/threads/{thread_id}/actions/{action_id}/confirm` (HITL Action decision)
   * `DELETE /v1/assistant/threads/{thread_id}`

3. **Account Lifecycle Endpoints (Existing)**:
   * `GET /v1/auth/me`
   * `GET /v1/me/export`
   * `DELETE /v1/me` (Payload: `{"confirmation": "DELETE", "refresh_token": "..."}`)

---

## 3. Frontend Component Architecture (`apps/web`)

### 3.1 `/dashboard` Page Structure
* `apps/web/app/(app)/dashboard/page.tsx`
* `apps/web/components/dashboard/dashboard-metrics-grid.tsx`
* `apps/web/components/dashboard/fsrs-forecast-chart.tsx` (Recharts integration)
* `apps/web/components/dashboard/quick-continue-card.tsx`

### 3.2 `/assistant` Page Structure
* `apps/web/app/(app)/assistant/page.tsx`
* `apps/web/components/assistant/thread-sidebar.tsx`
* `apps/web/components/assistant/chat-message-list.tsx`
* `apps/web/components/assistant/hitl-action-card.tsx` (Approve/Reject interactive buttons)
* `apps/web/hooks/use-assistant-stream.ts` (Custom EventSource/fetch reader for SSE stream)

### 3.3 `/settings` Page Structure
* `apps/web/app/(app)/settings/page.tsx`
* `apps/web/components/settings/profile-card.tsx`
* `apps/web/components/settings/data-export-card.tsx`
* `apps/web/components/settings/delete-account-modal.tsx`

---

## 4. Security & Error Handling
* All requests enforce Bearer JWT authentication.
* Account deletion requires typing `"DELETE"` and passing the active refresh token.
* HITL assistant actions check lease & checkpoint freshness before executing backend structural changes.
* Toast notifications via `sonner` for network errors, export failures, and deletion feedback.

---

## 5. Success Criteria & Verification
* `GET /v1/learning/dashboard` returns correct FSRS counts and 7-day forecast.
* `/dashboard` renders metric cards, Recharts forecast bar chart, and session continue button seamlessly.
* `/assistant` handles real-time message streaming and successfully executes HITL confirmations on actions.
* `/settings` exports valid JSON data and safely revokes session on confirmed account deletion.
