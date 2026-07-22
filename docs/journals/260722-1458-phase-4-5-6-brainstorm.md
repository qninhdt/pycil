# Technical Journal: Brainstorm Phase 4, 5 & 6 (Engagement, Assistant, Settings)

**Date:** 2026-07-22
**Author:** Antigravity AI
**Scope:** Phase 4, 5, 6 — `/dashboard`, `/assistant`, `/settings` Architecture & Wireup

## Key Decisions & Architecture
1. **`GET /v1/learning/dashboard` Endpoint**:
   - Added requirement for a single backend aggregation endpoint returning total learned words (`mastery > 0`), due today count (`next_review_date <= NOW()`), average mastery, a 7-day FSRS forecast histogram, and quick continue session info.

2. **`/assistant` HITL Stream Integration**:
   - Leverages Pycil's existing SSE stream endpoint (`/v1/assistant/threads/{id}/messages`).
   - Parses `action` events in real-time and renders inline HITL interactive cards in the chat stream.
   - User approval/rejection triggers `POST /v1/assistant/threads/{thread_id}/actions/{action_id}/confirm`.

3. **`/settings` Account Management**:
   - Displays user profile information.
   - Integrates `GET /v1/me/export` for instant JSON data dump download.
   - Integrates `DELETE /v1/me` with double-confirmation modal demanding text confirmation `"DELETE"`.

## Artifacts Produced
- Design Document: [`docs/designs/phase-4-5-6-engagement-assistant-settings.md`](file:///home/qninh/projects/pycil/docs/designs/phase-4-5-6-engagement-assistant-settings.md)
