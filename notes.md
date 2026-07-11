# System Redesign Notes: Real-Time & Asynchronous Task Architecture

This document notes identified flaws, limitations, and future improvements for the real-time communications and asynchronous processing systems in Pycil.

---

## 1. Identified Limitations in the Current SSE Design

* **Resource Utilization & Scalability:** 
  The current Server-Sent Events (SSE) system relies on the Go API holding open a persistent HTTP connection per request (relayed through Caddy). High numbers of concurrent users will cause significant memory usage and limit file descriptor scaling.
* **Caddy Buffering & Proxy Complications:**
  To prevent chunks from being buffered and delayed, Caddy requires explicit, custom configurations (`flush_interval -1` and headers like `X-Accel-Buffering: no`). This is fragile and error-prone during infrastructure updates.
* **Ad-hoc Pub/Sub Management:**
  Redis Pub/Sub is consumed directly inside Go handler goroutines. This lacks built-in support for message queue buffering, connection multiplexing, channel-based authorization, and presence tracking.
* **Incomplete Async Flows (e.g., LLM Grading):**
  Free-text/`WRITE` question grading requires asynchronous LLM validation. In V1, this flow is unimplemented (`StatusNotImplemented`) because managing async notification and session-lock handoffs to the frontend is difficult to sustain with the current primitive SSE setup.

---

## 2. Proposed Redesign: Migration to Centrifugo

To offload connection management and streamline all real-time events, we propose migrating from ad-hoc Go SSE + Redis Pub/Sub to **Centrifugo** (or a similar specialized real-time messaging server).

### Key Architectural Benefits
* **Offloaded Connection Management:** Centrifugo will run as a separate container in the `docker-compose` stack. The Go backend will no longer hold open thousands of persistent client connections.
* **Transport Protocol Versatility:** Supports WebSockets, SSE, and HTTP-streaming out of the box, handling fallback protocols automatically if WebSockets are blocked by client firewalls.
* **Stateful Connections & Reconnection Recovery:** Centrifugo caches messages, allowing clients that briefly disconnect to recover missed messages without re-querying the database.

### Channel Topography Design
* **Term Generation (`terms:{term_id}` or `jobs:{job_id}`):**
  Clients subscribe to a channel corresponding to their added term or job ID. When the Python worker finishes enriching the term, it publishes the structured result payload to the channel, instantly updating the user's deck table.
* **User Notifications (`users:{user_id}`):**
  A private, authenticated channel per user to receive real-time notifications, XP gains, daily streak achievements, or system announcements.
* **LLM Grading (`grading:{response_id}`):**
  For free-text `WRITE` answers, the client enqueues the submission and listens on the grading channel. The Python worker performs the LLM-judge verification and publishes the verdict back to the client via Centrifugo.

### Security and Authorization
* The Next.js frontend requests a subscription token from the Go API.
* The Go API generates a JWT-based subscription token signed with a shared Centrifugo secret.
* The client sends the token to Centrifugo to securely authorize subscription to private channels (e.g., `users:{user_id}`).

---

## 3. Proposed Redesign: OAuth & Session Architecture

To streamline security, remove token-signing coupling between Next.js and Go, and follow industry best practices, we propose a redesign of the authentication and session management flow.

### Key Architectural Guidelines

* **Backend-Driven OAuth:**
  Move the entire OAuth code exchange, state validation, and callback handling to the Go backend API. Next.js should not directly perform fetch-upsert synchronization. 
  *(Reference implementation: Refer to the standard OAuth flow implementation in `~/projects/openlet` for details.)*
* **Upgrade to OAuth 2.1:**
  Align with the upcoming OAuth 2.1 specification:
  * Mandate **PKCE (Proof Key for Code Exchange)** for all clients.
  * Disallow the Implicit Grant flow.
  * Enforce exact redirect URI string matching.
* **Backend-Signed JWTs:**
  The Go backend API must exclusively sign, manage, and validate all session JWT tokens. This eliminates the need to share `AUTH_JWT_SECRET` keys between the frontend and backend, reducing key exposure risk.
* **Migrate to `iron-session` on Frontend:**
  Replace Auth.js/NextAuth on the Next.js frontend with **`iron-session`**. Next.js will store the backend-issued JWT in a secure, stateless, encrypted cookie managed via `iron-session`, ensuring that session data is cryptographically sealed and client-side safe.

---

## 4. Proposed Redesign: Configuration Management

To clean up manual environment variable loading and add flexibility for different deployment structures, we propose a redesign of the configuration system in Go.

### Key Architectural Guidelines

* **Migrate to Viper (spf13/viper):**
  Adopt **Viper** as the central configuration engine in the Go API:
  * Enable multi-source config reading (support for environment variables, config files like `.yaml`/`.json`, and default fallbacks).
  * Automatically bind environment variables with keys via `viper.AutomaticEnv()`.
  * Support type-safe decoding into structural config objects using `viper.Unmarshal()`.
  * Open up potential for live-reloading configuration settings without restarting the backend process via `viper.WatchConfig()`.

---

## 5. Proposed Redesign: Infrastructure & Deployment

To simplify the deployment stack and remove redundant routing layers, we propose a redesign of the network ingress.

### Key Architectural Guidelines

* **Remove Caddy Container:**
  Eliminate the self-hosted Caddy reverse proxy from the `docker-compose.yml` stack.
* **Direct Exposure via Docker Compose:**
  Map and expose the Go API container port directly to the host (e.g., `8000:8000` or via a shared Docker network). Ingress concerns like SSL/TLS termination, rate limiting, and public caching should be offloaded to cloud providers (e.g., Cloudflare, AWS ALB) or managed via Next.js proxies.
* **API Routing & Security Transition:**
  * Since Caddy will no longer strip the `/api/core/*` prefix, the Next.js frontend should call backend paths directly, or Go's router must handle path prefixes natively.
  * Internal-only endpoints (such as `POST /auth/upsert-user`) must rely entirely on Go API token verification (`X-Internal-Secret`) for defense-in-depth since Caddy will no longer block public access to these paths.

---

## 6. Proposed Redesign: LLM Prompt Security & Input Sanitization

To secure the LLM worker against prompt injection and prompt leak attacks, we propose adopting the untrusted nonce-wrapping pattern (similar to the implementation in project `openlet`):

### Key Architectural Guidelines

* **Untrusted Content Nonce Wrapper:**
  Wrap all untrusted inputs (e.g., definitions, translations, or user-submitted texts sent to the LLM) in unique per-request cryptographic nonce delimiters: `<untrusted-{nonce}>...</untrusted-{nonce}>`.
* **Breakout Sanitization:**
  Before wrapping the content, escape any occurrence of `</untrusted` in the input (e.g., replacing with `</untrusted-escaped`) to prevent adversarial payloads from forging a closing tag.
* **Instruction Boundary Enforcement:**
  Instruct the LLM in its system prompts that any instructions inside `<untrusted-NONCE>...</untrusted-NONCE>` must be treated purely as data, and that the block only terminates at the matching cryptographic nonce.
* **Safety-Preserving Truncation:**
  If the input must be trimmed or truncated to fit token limits, parse the wrapper to truncate the inner text first and then re-apply the exact same matching nonce closing tag to preserve the safety boundary.
