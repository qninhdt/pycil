# Production latency and assistant investigation

Investigation date: 18 October 2026 UTC / 19 October 2026 Asia/Ho_Chi_Minh.
Status: routing and API/database timing comparisons recorded; application hot-path profiling and an equivalent public browser comparison remain open. Production routing and application code were not changed by this investigation. Assistant changes are deferred at the user's request while ordinary API latency is investigated.

## Confirmed production topology

- Frontend: Next.js on Vercel, compute in Singapore (`sin1`), with Cloudflare proxy enabled for `pycil.qninhdt.com` during measurement.
- API: Cloudflare → Caddy → two API containers on the VPS. The worker and PostgreSQL/Redis are on the same VPS.
- Observed edge identifiers were Singapore/Hong Kong. The evidence does not establish that requests are routed around the world.
- The frontend already supports a separate server-only `PYCIL_API_URL`; browser requests use `NEXT_PUBLIC_PYCIL_API_URL`. Co-located SSR can call API Docker DNS without sending those server requests through Cloudflare.
- Assistant SSE requests go from the browser directly to the API hostname. They do not pass through a Vercel function.

## HTTP benchmark

[Sanitized request measurements](measurements.json). Sequential requests with reused connections, excluding the first request of each arm from warm medians. These are small diagnostic samples, not load-test percentiles or browser rendering measurements.

Latest matched-source comparison (eight requests per arm; seven retained for each warm median):

| Authenticated `/app` route | Median TTFB | Median full HTTP response |
| --- | --- | --- |
| Cloudflare → Vercel | 230 ms | 473 ms |
| Vercel directly, same public Host/SNI | 249 ms | 449 ms |
| SSH tunnel → temporary Next.js on VPS → internal API | 106 ms | 397 ms |

All retained responses were authenticated HTTP 200. The self-hosted build was matched against 321 deployed source/config/public files, allowing only `output: standalone`; the builder and resulting artifacts differ from Vercel. Its container had a one-CPU/768-MiB cap and observed cgroup memory peak 136.7 MiB, with approximately 101 MiB resident at the final snapshot and no OOM. This is not a capacity or peak-concurrency measurement.

**The SSH route bypasses Cloudflare and has different transport behavior from the public frontend. Therefore 397 versus 473 ms cannot be presented as a proven production migration speedup.** A public, equivalent-route canary/browser test is still required before claiming that self-hosting will improve user-perceived latency. Keeping Cloudflare in front of a VPS frontend adds a path not exercised by this isolated test.

Earlier connection-reuse probes measured:

| Request | Existing public proxy | Bypass comparison |
| --- | --- | --- |
| `/privacy` on Vercel | 257 ms | 197 ms direct Vercel |
| Authenticated `/app` | 487 ms | 480 ms direct Vercel |
| Word search | 118 ms | 37 ms SSH → VPS origin |
| Authenticated `/v1/me` | 143 ms | 38 ms SSH → VPS origin |

The API bypass uses a different route and is not a measurement of Cloudflare's own processing time. Origin TLS was independently verified through the tunnel with Cloudflare's published Origin CA root for authenticated requests; public-origin access was never opened. Some earlier unauthenticated tunnel probes used a local verification bypass only.

Cold-connection probes produced approximately 230–350 ms median API/home TTFB from the operator machine, depending on endpoint. This includes connection setup and is not comparable to the warm medians above. Ordinary VPS-local origin probes were around 18 ms for liveness and 23 ms for search.

These observations do not establish Cloudflare or Vercel as the sole cause of broad UI slowness. They also do not measure script execution, hydration, Clerk UI initialization, layout shifts, interaction waterfalls or LCP; no live browser surface was available.

## API processing and host resources

### Follow-up: ordinary API paths, concurrency and database execution

[Sanitized API measurements](api-timings.json). These measurements use authenticated GET requests for the existing operator account, without creating jobs or changing application data. The origin client runs on the VPS host, outside the API container's CPU quota, and calls its private container IP. Public samples originate on the operator machine and use the existing Cloudflare API hostname. Each arm has a different transport path; their difference is not Cloudflare processing time alone.

| Endpoint | VPS-local median, five requests | Public warm median, five requests |
| --- | --- | --- |
| `/v1/me` | 12 ms | 114 ms |
| Word search, `hello`, reference results included | 180 ms | 281 ms |
| Study progress | 82 ms | 205 ms |
| Study activity | 18 ms | 122 ms |
| Review schedule | 66 ms | 204 ms |
| Personal nodes with summaries | 20 ms | 121 ms |
| Published nodes with summaries | 74 ms | Not measured in the public arm |

Public medians exclude the first connection-establishing request. All retained public responses were HTTP 200 over HTTP/2 through the Singapore Cloudflare edge. The first connection added approximately 43–52 ms for TCP and a further 59–74 ms for TLS. The warm public path adds roughly 100–140 ms over origin samples for these endpoints, with endpoint and scheduling variation.

The Home page has an account-data dependency followed by five concurrent API reads, with possible additional reference-target/author reads. That five-request batch took a median **219 ms locally** across five runs on one API instance. Its measured API cgroup CPU delta was 3.43 seconds over the complete sequential-plus-parallel test; there were **zero throttled periods** in this host-client arm. An earlier client running inside the API container competed with the server and did show throttling; that arm must not be used to blame production CPU limits.

A separate warmed five-request-per-endpoint run compared `pg_stat_statements` counters before and after each endpoint, without resetting counters:

| Endpoint | Median local request | Total PostgreSQL execution across five requests |
| --- | --- | --- |
| Account | 12.3 ms | 0.56 ms |
| Search | 180.0 ms | No SQL calls |
| Progress | 63.8 ms | 2.58 ms |
| Activity | 19.9 ms | 0.83 ms |
| Schedule | 73.2 ms | 2.93 ms |
| Personal nodes | 19.8 ms | 0.74 ms |
| Published nodes | 70.3 ms | 3.72 ms |

These counters cover the database, not a single isolated session; background readiness/other traffic can add calls, and the execution counters do not include client transport, planning, ORM work or event-loop scheduling. They nevertheless show that database execution is far too small to explain the observed request durations in this sample. Existing database client spans grew under concurrent requests; their duration cannot be equated with PostgreSQL execution time.

The follow-up resource snapshot showed about 5.2 GiB available RAM, 97–99% CPU idle and no active swap I/O. Together with the host-client cgroup check, this does not support adding RAM or blindly raising container quotas as the first fix. It does not exclude short CPU bursts or application CPU bottlenecks on a single event loop.

**There are two separate costs: the public network/proxy route, and backend application work, particularly search and the concurrent Home reads.** Profile the latter before changing its implementation. The aggregate 20-ms ordinary-request median below does not describe every endpoint or a concurrent page load.

The request paths are:

- Initial server rendering: browser → Cloudflare → Vercel/Next.js → public API/Cloudflare → Caddy → API.
- Browser API interactions: browser → Cloudflare → Caddy → API. Vercel is not a CRUD API proxy.
- Co-located server rendering could use Next.js → private API, removing the public API round trip from SSR. It would not remove browser-to-API latency or the measured backend processing costs.

The earlier **397-ms result is the full HTTP page response through an SSH-based hosting experiment**, not one API's processing time and not an actual browser paint measurement.

The captured ordinary HTTP completion logs, excluding health probes and assistant streams, contained 1,043 requests, median application processing time 20.18 ms, maximum 1,120.96 ms, only two above one second, and no HTTP 5xx responses in that set. This does not include browser rendering or network delay and does not establish latency under load.

At the initial host snapshot, roughly 5.5 GiB RAM was available on the 7.8 GiB VPS, swap was unused, and the inspected API/worker containers had no OOM or restart history. Individual containers were subsequently restarted outside this investigation, with the API/worker image remaining unchanged. This was not an idle, frozen production environment.

## Assistant and checkpoint diagnosis

There is one conversation/thread, with 136 checkpoint rows at inspection time. LangGraph persists steps within a conversation; one conversation is not one checkpoint row. The native checkpoint tables were queried read-only and decoded with `AsyncPostgresSaver`.

The latest decoded state ended with an assistant `generate_words` call and no matching tool result. Four tool calls in the inspected message history lacked persisted tool results. No pending checkpoint error was present in the latest state. These observations show incomplete turns, not proven database corruption.

Correlated events on 18 October, UTC:

| Tool start | Stream cancelled | Time after tool start |
| --- | --- | --- |
| 16:24:16.555 | 16:25:16.557 | 60.001 s |
| 16:50:16.936 | 16:51:16.936 | 60.000 s |
| 16:51:33.376 | 16:52:33.376 | 59.999 s |

Caddy logged downstream cancellation/incomplete responses at those points. The agent recorded cancellation. A separate run cancelled after approximately 11 seconds; an outbound `ReadError` was logged after that cancellation, so that exception alone does not prove the original cause.

The worker logs contained 31 successful word publications and no job-error events in the captured interval. Word generation took approximately 15–88 seconds. In one five-word batch, the final word completed 29 seconds after the agent disconnected. Another larger batch continued until 16:53:54 after its agent stream had already closed. The HTTP turn and the queued generation jobs have separate lifetimes.

The current tool waits for results up to 300 seconds, but its caller is cancelled when the stream disconnects. The checkpoint can therefore contain the tool call without its eventual result, even though words were generated successfully. Before another model call, the assistant boundary repairs missing results in model input using `tool_result_unavailable`; this can lead the assistant to describe a technical failure and submit work again. That repair does not persist the successful background result back into the interrupted turn.

### Confirmed gap and remaining uncertainty

The assistant uses `StreamingResponse` and sends no SSE heartbeat while it waits for the jobs. That can leave the stream silent for longer than a minute. Three cancellations align tightly with a 60-second wait, but the exact component enforcing that boundary has not been identified. There is no proof that Cloudflare imposes it: the documented default proxy read timeout is 125 seconds, and the inspected Caddy configuration and frontend fetch path did not contain a 60-second deadline.

The first cause-aligned change to validate is a heartbeat during silent tool waits, using SSE support from the installed framework rather than a new worker or hand-built heartbeat framework. FastAPI supports automatic idle pings on its native SSE generator route. Adapting this endpoint must preserve the existing AG-UI event encoding, error handling, cancellation, and billing settlement; simply wrapping already encoded SSE in another encoder would be incorrect. A browser-side disconnect trace and a controlled wait exceeding 60 seconds are still needed to prove the original cutoff and verify the fix.

Do not delete checkpoints, rebuild the database, or redesign the worker to address this evidence.

## Rendering and Cloudflare choices

Next.js running as a Node/Docker application on the VPS retains SSR, React Server Components and streaming. Self-hosting Next.js does not require converting the app to CSR.

| Choice | Relevant trade-off |
| --- | --- |
| Keep SSR and co-locate Next.js with the API | Removes the Vercel → public API round trip from server rendering. Browser API traffic and Clerk authentication still have their own network paths. |
| Convert protected pages to CSR | Moves data fetching after JavaScript/authentication startup in the browser; can add a waterfall. It is not an automatic latency improvement. |
| Keep the current hybrid rendering | Public/initial content can render on the server; filters, mutations and other interactions stay client-side. No broad rendering rewrite is required. |
| Keep Vercel | Use its native edge; an extra Cloudflare proxy is generally unnecessary and Vercel recommends avoiding this arrangement. The measured authenticated page did not materially improve merely by bypassing that proxy. |
| Host Next.js on the VPS | Keeping Cloudflare in front of public frontend/API endpoints still provides edge security. SSR can use the private API address, so those calls do not incur a public proxy hop. |

For the VPS API, disabling Cloudflare is a separate security/TLS change: the origin currently uses a Cloudflare Origin CA certificate and restricts public ingress to Cloudflare. Switching DNS to unproxied without replacing that trust/access setup would break direct clients. The SSH-origin comparison intentionally avoided changing either boundary.

## Source and deployment controls

The isolated build uses the deployed frontend source, the same installed dependency versions and Next.js 16.3.8, with `output: standalone`. It uses the webpack builder instead of Vercel's build artifact, so it is a hosting experiment, not an identical binary.

A new Vercel deployment was discovered during investigation. The first isolated build came from the preceding deployment and was treated as preliminary. The final repeated build is matched against the newer deployment `dpl_6KrpdAM9xQCzDRXzkogmmX8ijsvm` file hashes; the preceding deployment was `dpl_4JkoudMjvgajzZt1jicMTdZDXdVU`. Rejected authentication/redirect samples are excluded from retained measurements.

No paid LLM generations, synthetic jobs, conversation changes, DNS changes, firewall changes or production deployments were performed. Both temporary frontend containers, their runtime environment/build files on the VPS, the pulled temporary Node image, and owned SSH tunnels were removed after measurement. Private local raw conversations/logs and credential files were removed after retaining sanitized aggregates.

## Recommendation

1. Keep the current hybrid SSR/client rendering. A CSR rewrite has no demonstrated benefit here.
2. Do not migrate the frontend solely on the current latency numbers. VPS self-hosting is technically viable and has room at the observed light load, but its public-route performance has not been established.
3. If keeping Vercel, use DNS-only for the frontend as Vercel recommends; treat this as removing an unnecessary proxy layer, not a demonstrated cure for the whole app. No DNS change was performed.
4. Keep Cloudflare protection for the VPS API at present. If the frontend later moves to the VPS, use the existing private server-only API URL for SSR; evaluate public proxy latency separately from SSR placement.
5. Prioritize ordinary API application profiling: search takes about 180 ms without SQL, while several study/library endpoints spend much more time outside PostgreSQL execution than inside it. Retain the existing assistant diagnosis for later; do not mix that separate issue into the API latency comparison or infer checkpoint corruption from unfinished tool calls.

## Sources

- [Next.js self-hosting](https://nextjs.org/docs/app/guides/self-hosting) and [deployment support](https://nextjs.org/docs/app/getting-started/deploying).
- [Vercel: Cloudflare with Vercel](https://vercel.com/kb/guide/cloudflare-with-vercel).
- [Cloudflare connection limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/).
- [FastAPI SSE and automatic idle pings](https://fastapi.tiangolo.com/tutorial/server-sent-events/).
- [LangGraph checkpoint reference](https://reference.langchain.com/python/langgraph.checkpoint).

Application paths inspected: `apps/web/src/lib/api/services/config.ts`, `apps/web/src/lib/api/services/server.ts`, `apps/web/src/lib/api/services/assistant.ts`, `apps/api/pycil/assistant/api.py`, `apps/api/pycil/assistant/stream.py`, `apps/api/pycil/assistant/tools.py`, and `apps/api/pycil/assistant/graph.py`.
