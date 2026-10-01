# Content jobs: best-effort background execution

Word generation and question supply run through FastAPI `BackgroundTasks` in the
API process after the HTTP response. They are **not durable jobs**: process restart,
deploy, or VPS outage can abandon accepted work. A learner can request it again;
there is no queue, automatic replay, scheduler, worker service, or job table.
Assistant turns stay inline in the authenticated streaming request. Redis remains
necessary for study sessions, coordination, deduplication, and job receipts.

## Receipt contract

The API writes `pycil:job:{job_id}` before responding, with a 24-hour TTL, owner,
kind, `createdAt`, status, result and error code. It then attaches the content
callback to the response. `GET /v1/jobs/{job_id}` requires the owner and returns
the same 404 for missing and foreign IDs. Status is `queued`, `running`, `done`,
`failed`, or `expired`. An unfinished receipt older than the job deadline reads as
`expired` rather than leaving the client polling forever. The receipt disappears
after its TTL. Errors expose codes, never provider exception details.

Each callback creates and closes its own Lexi and Redis resources; no request DB
session is held after the response. Work is bounded by a job timeout. A terminal or
stale receipt cannot be overwritten by a late callback. A crashed process cannot
finish a callback, and there is no startup scan to resume one.

Question supply keeps the session's bounded prepare attempts and cooling period.
An expired receipt no longer counts as in-flight for that round; a later request
may try again within the attempt bound. Concurrent word requests still use Redis
singleflight, and Lexi's content identity prevents duplicate persisted content.
These mechanisms do not promise exactly-once provider billing after a crash.

This trades crash recovery for a smaller single-VPS deployment. If the product
requires completion across API restarts or independent worker scaling, restore a
proper broker/worker instead of adding an ad-hoc queue to the API.
