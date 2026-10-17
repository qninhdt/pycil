/** Public browser policy only. Changes take effect after the web build/redeploy. */
export const webConfig = {
  query: {
    // Query freshness per browser cache entry, in ms. 60,000 is one minute;
    // >= 0; increasing reduces refetches but keeps stale responses longer.
    staleMs: 60_000,
    // Inactive query retention in ms. 300,000 is five minutes; >= 0.
    // Increasing retains more data in browser memory between views.
    gcMs: 300_000,
    // Extra transient query attempts after the first, integer >= 0.
    // 1 permits one retry; increasing adds traffic/latency. Mutations never retry.
    retries: 1,
    // Public profile/library heading freshness in ms, >= 0. Five minutes
    // preserves the existing override for infrequently changing headings.
    publicHeadingStaleMs: 300_000,
    // Assistant thread-detail recovery attempts, integer >= 0. 3 preserves
    // checkpoint recovery retries; 404 remains terminal in the caller.
    conversationRetries: 3,
  },
  search: {
    // Supported dictionary/picker input length in characters, integer 1..256.
    // 256 matches the existing API ceiling; increasing requires an API contract change.
    maxQueryChars: 256,
  },
  requests: {
    // Default API metadata request deadline in ms, > 0. 12 seconds includes
    // token acquisition. Higher values tolerate slower responses but delay errors.
    timeoutMs: 12_000,

  },
  polling: {
    // Home report refresh interval in ms, > 0. One minute preserves report
    // freshness; lower values increase aggregation traffic.
    homeMs: 60_000,
    // Local home clock tick in ms, > 0. One minute updates relative dates
    // without fetching data; independent from the report refresh interval.
    clockMs: 60_000,
  },
  pagination: {
    // Library/discovery page size, integer 1..100 per request. 12 preserves
    // the current grid; larger pages increase payload and rendering work.
    library: 12,
    // Destination/source picker page size, integer 1..100. 20 preserves
    // picker behavior; larger pages increase payload and selection options.
    picker: 20,
    // Small home library preview, integer 1..100. 4 preserves the preview;
    // increasing adds content and requests for reference metadata.
    preview: 4,
    // Flashcard fetch page size, integer 1..100, per pagination request.
    // 100 uses the supported API ceiling; reducing adds pagination requests.
    flashcards: 100,
    // Conversation list page size, integer 1..100. 20 preserves the sidebar;
    // larger pages increase metadata payloads.
    conversations: 20,
  },
  study: {
    // Questions shown in each browser study round, integer > 0. 8 preserves
    // round flow; changing it changes learner behavior and recap cadence.
    roundSize: 8,
    // Stored study-session retention in days, > 0. Seven days preserves resume
    // behavior; increasing retains local data longer. Does not alter server history.
    retentionDays: 7,
    // Maximum attempts per question occurrence, integer > 0. 3 preserves retry
    // and completion behavior; increasing changes learner workload.
    maxAttempts: 3,
  },
  auth: {
    // Clerk loading fallback deadline in ms, > 0. 12 seconds preserves the
    // unavailable-state timing; independent from server identity request deadlines.
    loadingTimeoutMs: 12_000,
  },
  preferences: {
    // Locale cookie lifetime in seconds, > 0. 31,536,000 is 365 days;
    // increasing remembers the preference longer. Available locales stay registry-owned.
    localeCookieSeconds: 31_536_000,
  },
  assistant: {
    // Client message bound in characters, integer > 0. 8,000 matches the backend
    // assistant policy; keep them aligned. Higher values permit larger model inputs.
    maxMessageChars: 8_000,
    // Serialized assistant request ceiling in bytes, integer > 0. 15 MB matches
    // backend/ingress body limits; increasing permits larger image uploads.
    maxBodyBytes: 15_000_000,
  },
} as const

// Public local-development fallback only; explicit server/browser URLs still win.
// 127.0.0.1:8000 targets the documented local API. Changing it requires a web rebuild.
export const localApiOrigin = 'http://127.0.0.1:8000'
