---
phase: 9
title: "Agent"
status: pending
priority: P1
effort: "5-6d"
dependencies: [2, 3, 4, 6, 7]
---

# Phase 9: Agent

## Overview

Move the graph loop out of the HTTP request into a durable Run claimed by a worker,
replace the approval subsystem with `interrupt()` plus one resume endpoint, and add
the three behaviours the agent has never had: compaction, untrusted-content wrapping,
and a stable prompt prefix.

The largest phase, and the last one before the client.

## Requirements

**Functional**

- A Run is a **durable queued row** (`G1`); the command returns a handle (`G2`).
- Runs execute on their own queue in their own worker (`G3`), bounded by
  `--max-async-tasks` as the global admission gate (`G4`).
- Claim with `SKIP LOCKED`, hold a **lease with a heartbeat**, **fence** every write
  (`G5`).
- A reaper requeues an expired lease; the worker resumes **from the checkpoint**, not
  from input (`G6`). Lease expiry is **not terminal** (`G7`).
- Cancellation is a **column**, observed at the next yield point (`G8`).
- HITL kept (`G9`) as `interrupt()` + a popup + one resume endpoint (`G10`); a paused
  Run holds **no worker slot** (`G11`).
- `partial_output` persisted every N tokens or M milliseconds (`E6`).
- Tokens go to `thread:<threadId>` (`E3`); no second streaming path.
- **Compaction** mandatory, by context-window ratio, never splitting a tool call from
  its result (`G12`).
- **Every external string wrapped** so the model treats it as data (`G13`).
- Prompt caching by **prefix stability** (`G14`); log the cache-read token count
  (`G15`).
- The system prompt written against a corpus of real ones (`G16`, `[R39]`).

**Non-functional**

- One running Run per Thread, enforced by a unique index — tested as a lock.
- Every tool re-checks ownership at execution, independent of approval.
- No sandbox (`G17`).

## Architecture

```text
POST /v1/agent/threads/{id}/messages
  BEGIN
    INSERT runs(status='queued', thread_id, fence=0)
      ← unique index rejects a second active Run → 409
    INSERT outbox(subject='agent.run.execute', payload={runId})
  COMMIT                                          → 202 {runId}

relay    claim SKIP LOCKED → publish → mark

worker   UPDATE runs SET status='running', lease_owner=me,
                lease_expires_at=now()+ttl, fence=fence+1
          WHERE id=$1 AND status='queued'
         0 rows → ack and drop        (duplicate delivery)

execute  load checkpoint → RESUME, not rerun
         node boundary          → checkpointer writes
         every N tokens / M ms  → partial_output (fenced)
         token deltas           → thread:<threadId>
         heartbeat              → extend lease
         yield point            → check cancellation

finish   write output or error, clear partial fields, release lease
```

**Four motions on one row**, each following from the previous: admission (unique
index), claim (conditional update, fence+1), lease (heartbeat), fence (every write
matches run and fence). Admission alone wedges a Thread when a worker dies; a lease
alone lets a paused worker overwrite its successor.

**Idempotency with no dedup table.** A duplicate delivery matches zero rows on the
conditional claim. A crash resumes from the checkpoint, so a tool that already ran
has its result in state. A stalled worker's late write is rejected by the fence.
Single-writer stops concurrency; the checkpoint stops redoing.

**Approval:**

```text
tool call needs approval
  → interrupt() pauses inside the node; the checkpoint holds the state
  → status = interrupted, holding NO worker slot
  → the panel renders a popup from the interrupt payload
       approve → POST /v1/agent/runs/{runId}/resume → the tool executes
       reject  → the agent receives a rejection and CONTINUES
```

Reject is not cancel. The agent learns it was refused and can propose something else.

What this does **not** need: an action table as a state machine (the checkpoint *is*
the state), a time-to-live and an expiry reconciler (a paused Run holds no slot; the
general reaper handles a very old interrupt), a freshness check (the tool re-checks
ownership when it runs — a node deleted meanwhile raises, and the agent handles it),
or an audit row (Postgres holds the state; the popup is the mechanism).

## Related Code Files

**Create**

- `apps/api/pycil/agent/` — flat module (`A2`), renamed from `assistant`
- `apps/api/pycil/agent/runs.py` — create, claim, lease, fence, cancel, resume
- `apps/worker/pycil_worker/jobs/run_agent.py` — the worker-side loop
- `apps/worker/pycil_worker/jobs/reap_runs.py` — lease expiry → requeue
- `apps/api/pycil/agent/compaction.py` — ratio-triggered, tool-call-safe
- `apps/api/pycil/agent/untrusted.py` — the structural wrapper
- `apps/api/pycil/agent/prompt.py` — the system prompt, written per `[R39]`

**Modify**

- the tool set — approval on move, publish, delete, remove-sense; every tool
  re-checks ownership
- the checkpointer — unchanged in mechanism, its thread key built by one named builder
- `docker-compose.yml` — `agent-worker` already added in phase 2; set its
  `stop_grace_period` above the run deadline

**Delete**

- the SSE module and its framing
- the request-bound streaming path
- the action table's service, its confirm endpoint, the TTL, the expiry reconciler,
  the freshness check
- the persisted run-event reads and their cursor endpoint

## Implementation Steps

1. Write `runs.py`: create (unique index rejecting a second active Run), claim
   (conditional, fence+1), heartbeat, fence check on every write, cancel column.
2. Write the worker loop: load the checkpoint and **resume**. Verify it does not rerun
   from input — this is the property `F3` exists to protect.
3. Add `partial_output` persistence on a token/time trigger, written under the fence.
4. Publish the event contract to `thread:<threadId>`: started, message delta, thinking
   delta, tool started, tool args delta, tool completed, approval required, message
   completed, terminal.
5. Write the reaper: expired lease → `queued` → outbox row → another worker resumes.
6. Wire cancellation: the column, and a yield-point check inside the loop.
7. Convert the four destructive tools to `interrupt()`; write the single resume
   endpoint handling approve and reject.
8. Delete the action subsystem — table service, confirm endpoint, TTL, reconciler,
   freshness check.
9. Write `compaction.py`: trigger on a context-window ratio, summarise the oldest safe
   range, and **never** split a tool call from its result.
10. Write `untrusted.py`: a structural wrapper applied once at the boundary where an
    external value enters a tool result. Not an escaping filter — a filter is a
    blocklist and loses to the next encoding.
11. Write `prompt.py` against `[R39]`, with a stable prefix: no timestamp, no random
    id, a tool list that never changes mid-session (an unavailable tool returns a
    typed refusal rather than disappearing), deterministic serialisation, thinking
    blocks returned with tool results.
12. Log the cache-read token count on every call.
13. Delete the SSE module and the request-bound path.

## Todo

- [ ] `runs.py`: admission, claim, lease, fence, cancel
- [ ] Worker loop resumes from the checkpoint
- [ ] `partial_output` on a token/time trigger, fenced
- [ ] Event contract published to `thread:<threadId>`
- [ ] Reaper: expired lease → requeue → resume
- [ ] Cancellation column plus yield-point check
- [ ] Four destructive tools use `interrupt()`
- [ ] One resume endpoint: approve and reject
- [ ] Action subsystem deleted
- [ ] `compaction.py`, tool-call-safe
- [ ] `untrusted.py`, structural, applied at the boundary
- [ ] `prompt.py` per `[R39]`, stable prefix
- [ ] Cache-read token count logged
- [ ] SSE module and request-bound path deleted
- [ ] `agent.md` §13 covered by named tests

## Success Criteria

- [ ] A duplicate claim matches zero rows
- [ ] A second Run on one Thread → 409
- [ ] Lease expiry → reaper → requeue → resume **from the checkpoint**
- [ ] A stalled worker's late write is rejected by the fence
- [ ] Cancellation mid-generation stops at the next yield point
- [ ] Two workers on one queue: no Run executes twice
- [ ] A destructive tool cannot execute before approval
- [ ] Reject → the agent receives the refusal and continues
- [ ] An interrupted Run holds no worker slot
- [ ] A node deleted during approval → the tool raises; the agent handles it
- [ ] `partial_output` written mid-generation and readable over HTTP
- [ ] Compaction never splits a tool call from its result
- [ ] An external string in a tool result is wrapped
- [ ] A node named like an instruction does not cause a destructive tool call
- [ ] A tool refusal does not change the tool list
- [ ] `agent.md` §13 fully covered by named tests

## Risk Assessment

**Resume-not-rerun is the property most likely to be silently wrong.** A loop that
loads a checkpoint and then replays the input produces plausible output while billing
twice. Signal: a resumed Run whose tool executed a second time. Response: the test is
"kill mid-run, resume, assert the tool ran once" — a real kill, not a mocked one.

**`untrusted.py` reduces probability, not risk.** Wrapping makes an injection less
likely to be obeyed; it does not make it impossible. The control that makes the
residual acceptable is approval on every destructive tool. Signal: a scripted-provider
test where an injection payload steers a destructive call. Response: that test is a
success criterion, and it is the reason approval is kept (`G9`) rather than removed as
the reference design does.

**Prefix stability is invisible when broken.** A timestamp in the prompt, a tool list
that changes, non-deterministic serialisation — each silently disables caching and
raises cost with no error. Signal: the cache-read count is always zero. Response:
logging it is the only detection available, which is why `G15` is a requirement rather
than an observation.

**Approval could be reintroduced as a subsystem.** The pull toward an action table is
strong because it feels auditable. Signal: a table appearing to track approval state.
Response: the checkpoint is the state; an audit row blocks nothing. If auditing is
genuinely wanted later it is a log line, not a state machine.

**A paused Run holding a slot would be an easy bug.** Signal: worker slots occupied by
runs doing nothing. Response: the job **ends** at the interrupt and approval enqueues
a new one — a criterion, not an optimisation, because a human lunch break otherwise
consumes capacity.
