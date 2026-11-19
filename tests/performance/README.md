# VPS performance workloads

The official **k6 2.3.0** image is pinned by digest in
[run-k6.py](../../scripts/run-k6.py). No API/worker code changes or additional
VPS services are required. The generator runs on an independent Linux machine,
with 1.5 CPU / 2 GiB RAM / no swap, a 64 MiB temporary filesystem, a run deadline
and a 2 GiB output limit. Do not run it on the application VPS.

## Prepare

1. Start with the provisional 2 API / 1 worker / 4 concurrent-job baseline, or
   record the deliberately selected topology for a controlled comparison. Record the real
   active source SHA, image digest and configuration; avoid deploys, backups,
   rebuilds and provider jobs during the measurement window.
2. Provision a [private fixture](fixtures/README.md), not copied personal tokens.
3. Get the running Prometheus container's private IP through operator SSH:

   ```sh
   ssh qninh@103.173.227.135 \
     "sudo -n docker inspect --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' pycil-production-prometheus-1"
   ```

4. Forward it to a free deterministic local port in a foreground terminal:

   ```sh
   ssh -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -N \
     -L 127.0.0.1:19090:<private-prometheus-IP>:9090 qninh@103.173.227.135
   ```

   The existing internal remote-write receiver is reached through encrypted SSH.
   There is no public telemetry endpoint or firewall change. The runner uses
   loopback HTTP inside this tunnel. Stop the tunnel after the run. Redis,
   PostgreSQL and collector ports remain private.

## Check and run

```sh
make k6-check
make k6-vps K6_ARGS='--scenario smoke --cohort db-read \
  --fixture /private/fixture.json --version <actual-deployed-SHA> \
  --ssh-host qninh@103.173.227.135 \
  --prometheus-url http://127.0.0.1:19090 --output /private/new-smoke-directory'
```

Use a new output directory whose parent already exists. k6 preflight checks every
word and identity/scope before timing; these requests have `phase=preflight` and
are excluded from business thresholds. Every business iteration makes exactly
one request: **60% word / 20% account / 20% progress**. The separate `--cohort search`
uses the same scenario executors for dictionary search only. `--cohort app-read`
uses ten equally weighted reads covering owned library details/senses/listing,
discovery, public profiles, usage, study activity/schedule and assistant
models/conversations. `--cohort mixed` combines equal shares of the three read
cohorts, preserving their internal route rotation. Each route has a response
contract checked in preflight.
These read cohorts never submit jobs, grades answers, writes study results or calls a paid model.

| Scenario | Offered load |
| --- | --- |
| `smoke` | 1 RPS for 2 minutes |
| `load` | 10 warm-up → 50 and 75 plateaus → recovery |
| `stress` | 25/50/75/100/150 steps → recovery |
| `spike` | 10 → 100 → 10 |
| `capacity` | 50/100/200/400 RPS, two-minute plateaus → recovery |
| `steady` | 15-second ramp → 200 RPS for three minutes → 75 seconds at 10 RPS |

Only smoke is enabled by default. Others require `--window-approved` after
lower-rate evidence and a reviewed production window; the flag does not prove
approval, backup freshness or safe target rates. Do not run the higher scripts
unattended. Operator review of each plateau and trailing one-minute windows is
still required; cumulative thresholds are not rolling windows. The `capacity`
scenario additionally isolates each rate in its own native k6 scenario and
aborts on p95/p99/error threshold failure after the ramp and one minute of
samples. An aborted run has no measured recovery plateau; verify readiness
separately after stopping.

The runner polls existing Prometheus signals and native read-only Docker stats
over SSH. It refuses missing signals and stops after 30 seconds of unsafe host
memory (<15% available), container memory (>90%), disk (<10 GiB or projected
exhaustion in six hours), WAL backlog (>300 seconds), stale/missing telemetry,
or competing jobs. An intentional worker-contention experiment may supply
`--max-job-backlog N` (0–128) for its known bounded batch; the default remains
zero and all other guards remain active. The chosen ceiling is recorded in run
metadata. Read workloads never create these jobs. Missing monitoring, deadline and output exhaustion stop the
run immediately. k6 also aborts on sustained cumulative >5% HTTP failures.
401/403 stop the run as authentication/edge-policy problems. The operator must
watch runner CPU/memory and dropped iterations; generator saturation invalidates
the capacity conclusion. `Ctrl-C` stops only the runner container.

An origin comparison is optional: first temporarily allowlist the runner IP,
then use `--origin-ip <IP>`. It preserves HTTPS hostname/SNI and certificate
verification. An untrusted Cloudflare Origin CA certificate needs an explicitly
trusted CA; never disable TLS verification. Revoke the allowance afterwards.

## Read results

The private output directory contains:

- `summary.json`: k6 aggregates and threshold verdicts; use metrics tagged
  `phase:business`, not aggregates polluted by preflight.
- `samples.json.gz`: timestamped client measurements for plateau/window analysis.
- `resources.jsonl`: server resource signals, native container and generator stats.
- `metadata.json`, `k6.log`: UTC interval, exit status, pinned image, release,
  dataset/script hashes and diagnostics. The runner checks deployed API/worker
  revisions against `--version`, records container identities and the mounted
  configuration hash before/after, and verifies received remote-write series.

In Grafana's Prometheus Explore, filter k6 series by the metadata `run_id`, for
example `k6_http_req_duration_p95{run_id="...",phase="business"}` and
`k6_http_reqs_total{run_id="...",phase="business"}`. Percentile gauges describe
this single generator; do not average percentiles across runners. Compare with
the existing API RED, stores and host dashboards over the same UTC interval.
Preserve output before retention expires; review/sanitize before sharing or S3
archival. No bearer token or user ID is a metric label.

Acceptance targets from the design are p95 <300 ms, p99 <800 ms, errors <1%,
correct responses and zero dropped iterations. A failed threshold stays failed;
HTTP 200 alone does not establish acceptable latency or capacity.
The latency thresholds apply to each bounded business route as well as the
aggregate, so frequent fast routes cannot hide a slower low-volume route.

Current production includes caches. These scripts measure that deployed system;
they do not manufacture a raw-DB baseline by flushing coordination Redis or
changing production cache policy.
