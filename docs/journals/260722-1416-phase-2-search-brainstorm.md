# Technical Journal: Phase 2 Search Page Brainstorming

- **Date**: 2026-07-22
- **Topic**: Phase 2 — Page `/search` & Backend Integration
- **Brainstorm Report**: [260722-1416-phase-2-search-page-brainstorm.md](file:///home/qninh/projects/pycil/plans/reports/260722-1416-phase-2-search-page-brainstorm.md)

## Key Technical Decisions Made

1. **Single-Page Dynamic Layout**: Chose single-page search interface with debounced dictionary search (300ms) over a complex split view.
2. **AI Job Tracking**: Centrifugo realtime WebSocket/SSE subscription with fallback polling (`GET /v1/jobs/{jobId}` every 2.5s) for smooth UX during AI generation.
3. **Deck Sense Modal**: Dialog popup to browse user decks (`GET /v1/decks`) and attach word senses (`POST /v1/decks/{node_id}/senses`).
4. **Empty State & Quota Handling**: Auto prompt user to generate with AI when dictionary search returns 0 results, handle HTTP 429 quota limits gracefully.
