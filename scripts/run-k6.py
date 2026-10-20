"""Run bounded, authenticated VPS read workloads using the official k6 image."""

import argparse
import base64
import hashlib
import ipaddress
import json
import math
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD = ROOT / "tests/performance"
IMAGE = "grafana/k6:2.3.0@sha256:9c2dee7f8ed74d317e4027c06a10f169b625638189de8d4555d0b3486a5aeb34"
# Scenario runtime plus setup and graceful-stop budgets; tokens need another five minutes.
SCENARIOS = {
    "smoke": ("01-smoke-test.js", 250),
    "load": ("02-load-test.js", 1450),
    "stress": ("03-stress-test.js", 1990),
    "spike": ("04-spike-test.js", 1092),
    "capacity": ("05-capacity-test.js", 800),
    "steady": ("06-steady-test.js", 440),
}
QUERIES = {
    "available_memory_ratio": "min(node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)",
    "disk_available_bytes": (
        'min(node_filesystem_avail_bytes{mountpoint="/",fstype!~"tmpfs|overlay"})'
    ),
    "disk_time_to_full": (
        "min(predict_linear(node_filesystem_avail_bytes"
        '{mountpoint="/",fstype!~"tmpfs|overlay"}[15m],21600))'
    ),
    "wal_backlog_seconds": 'max(pycil_wal_backlog_oldest_seconds{cluster="vps"})',
    "telemetry_age_seconds": (
        'time()-max(timestamp(http_server_duration_milliseconds_count{service_name="pycil-api"}))'
    ),
    "telemetry_missing": 'max(pycil:telemetry_missing:condition{env="vps"})',
    "job_backlog": 'max(pycil:jobs_backlog{env="vps"})',
}


def query(base, expression):
    with urlopen(
        base.rstrip("/") + "/api/v1/query?" + urlencode({"query": expression}),
        timeout=5,
    ) as response:
        data = json.load(response)
    rows = data.get("data", {}).get("result", [])
    if data.get("status") != "success" or len(rows) != 1:
        raise ValueError("Missing or ambiguous monitoring signal")
    value = float(rows[0]["value"][1])
    if not math.isfinite(value) or time.time() - float(rows[0]["value"][0]) > 90:
        raise ValueError("Stale or invalid monitoring signal")
    return value


def unsafe(values, max_job_backlog=0):
    return (
        values["available_memory_ratio"] < 0.15
        or values["disk_available_bytes"] < 10 * 1024**3
        or values["disk_time_to_full"] < 0
        or values["container_memory_ratio"] > 0.9
        or values["wal_backlog_seconds"] > 300
        or values["telemetry_age_seconds"] > 90
        or values["telemetry_missing"] > 0
        or values["job_backlog"] > max_job_backlog
    )


def validate_tokens(fixture, issuer, minimum_expiry):
    # Inspect expiry early; real API requests still verify signatures and ownership.
    for user in fixture["users"]:
        raw = user["token"].split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if (
            claims.get("iss") != issuer
            or not claims.get("sub")
            or claims.get("exp", 0) < minimum_expiry
        ):
            raise ValueError("Wrong token issuer or insufficient lifetime")
        if abs(datetime.fromisoformat(user["expires_at"]).timestamp() - claims["exp"]) > 1:
            raise ValueError("Fixture expiry does not match the token")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="smoke")
    parser.add_argument(
        "--cohort",
        choices=["db-read", "search", "app-read", "mixed"],
        default="db-read",
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--api", default="https://api-pycil.qninhdt.com")
    parser.add_argument("--issuer", default="https://clerk.pycil.qninhdt.com")
    parser.add_argument("--version", required=True, help="Actual deployed SHA or digest")
    parser.add_argument("--prometheus-url", required=True, help="Loopback SSH tunnel to Prometheus")
    parser.add_argument(
        "--ssh-host",
        required=True,
        help="VPS operator for read-only native container stats",
    )
    parser.add_argument(
        "--origin-ip", help="Previously allowlisted origin; verified TLS/SNI retained"
    )
    parser.add_argument("--window-approved", action="store_true", help="Required beyond smoke")
    parser.add_argument("--output", type=Path, required=True, help="New private evidence directory")
    parser.add_argument(
        "--max-job-backlog",
        type=int,
        default=0,
        help="Expected bounded jobs during an intentional contention test",
    )
    args = parser.parse_args()
    if not 0 <= args.max_job_backlog <= 128:
        parser.error("Expected job backlog must be between 0 and 128")
    if args.scenario != "smoke" and not args.window_approved:
        parser.error("Load/stress/spike need a reviewed maintenance window and lower-rate evidence")
    api, prometheus = urlsplit(args.api), urlsplit(args.prometheus_url)
    if (
        api.scheme != "https"
        or not api.hostname
        or api.username
        or api.password
        or api.path not in ["", "/"]
        or api.query
        or api.fragment
        or prometheus.scheme != "http"
        or prometheus.hostname not in ["127.0.0.1", "::1"]
    ):
        parser.error("Use an HTTPS API and loopback-only Prometheus SSH tunnel")
    if not re.fullmatch(r"[a-zA-Z0-9:._-]{7,128}", args.version):
        parser.error("Invalid deployed version")
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.@-]+", args.ssh_host):
        parser.error("Invalid SSH host")
    if args.origin_ip:
        ipaddress.ip_address(args.origin_ip)
    fixture_path = args.fixture.resolve()
    if fixture_path.stat().st_mode & 0o077:
        parser.error("Fixture must be private (chmod 600)")
    fixture = json.loads(fixture_path.read_text())
    script, duration = SCENARIOS[args.scenario]
    minimum_expiry = time.time() + duration + 300
    validate_tokens(fixture, args.issuer, minimum_expiry)
    if shutil.disk_usage(args.output.parent).free < 3 * 1024**3:
        parser.error("Runner needs at least 3 GiB free output space")
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    run_id = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + args.cohort
    metadata = {
        "run_id": run_id,
        "scenario": args.scenario,
        "cohort": args.cohort,
        "target": args.api,
        "path": "origin" if args.origin_ip else "edge",
        "version": args.version,
        "k6_image": IMAGE,
        "dataset_hash": fixture["dataset_hash"],
        "script_hashes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in WORKLOAD.glob("*.js")
        },
        "started_at": time.time(),
        "max_job_backlog": args.max_job_backlog,
    }
    runtime = output / "runtime.env"
    runtime.write_text(
        "\n".join(
            [
                f"API_BASE_URL={args.api}",
                f"VERSION={args.version}",
                f"RUN_ID={run_id}",
                f"COHORT={args.cohort}",
                f"TEST_PATH={metadata['path']}",
                "FIXTURE_FILE=/fixture.json",
                f"MINIMUM_EXPIRY={minimum_expiry * 1000}",
                f"ORIGIN_IP={args.origin_ip or ''}",
                f"K6_PROMETHEUS_RW_SERVER_URL={args.prometheus_url.rstrip('/')}/api/v1/write",
                "K6_PROMETHEUS_RW_TREND_STATS=med,p(95),p(99),avg,count,sum",
                "K6_PROMETHEUS_RW_STALE_MARKERS=true",
            ]
        )
        + "\n"
    )
    container = "pycil-k6-" + run_id.lower()
    command = [
        "docker",
        "run",
        "--rm",
        "--name",
        container,
        "--network",
        "host",
        "--read-only",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "128",
        "--cpus",
        "1.5",
        "--memory",
        "2g",
        "--memory-swap",
        "2g",
        "--ulimit",
        "fsize=2147483648:2147483648",
        "--tmpfs",
        "/tmp:size=64m",
        "--env-file",
        str(runtime),
        "-v",
        f"{WORKLOAD}:/workload:ro",
        "-v",
        f"{fixture_path}:/fixture.json:ro",
        "-v",
        f"{output}:/output",
        IMAGE,
        "run",
        "--no-usage-report",
        "--out",
        "experimental-prometheus-rw",
        "--out",
        "json=/output/samples.json.gz",
        "/workload/" + script,
    ]
    process = None

    def deployment():
        return subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                args.ssh_host,
                "set -e; sudo -n docker inspect --format "
                "'{{.Id}} {{.Config.Image}} {{index .Config.Labels "
                '"org.opencontainers.image.revision"}} {{.State.StartedAt}}' + "' "
                "$(sudo -n docker ps -q --filter name=pycil-production-api "
                "--filter name=pycil-production-worker); "
                "sudo -n sha256sum /etc/pycil/config.yaml",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout

    def sample():
        values = {
            name: query(args.prometheus_url, expression) for name, expression in QUERIES.items()
        }
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=5",
                args.ssh_host,
                "sudo -n docker stats --no-stream --format '{{json .}}'",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        containers = [json.loads(line) for line in result.stdout.splitlines()]
        containers = [c for c in containers if c["Name"].startswith("pycil-production-")]
        if not containers:
            raise ValueError("No production container resource samples")
        values["container_memory_ratio"] = max(
            float(c["MemPerc"].strip("%")) / 100 for c in containers
        )
        return values, containers

    try:
        metadata["deployment_before"] = deployment()
        releases = metadata["deployment_before"].splitlines()[:-1]
        if not releases or any(args.version not in row for row in releases):
            raise ValueError("Requested version differs from deployed API/worker")
        values, containers = sample()
        if unsafe(values, args.max_job_backlog):
            raise ValueError("Preflight monitoring reports unsafe or unhealthy production")
        with (
            (output / "k6.log").open("w") as log,
            (output / "resources.jsonl").open("w") as resources,
        ):
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            bad_since = None
            while process.poll() is None:
                values, containers = sample()
                stats = subprocess.run(
                    [
                        "docker",
                        "stats",
                        "--no-stream",
                        "--format",
                        "{{json .}}",
                        container,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
                resources.write(
                    json.dumps(
                        {
                            "time": time.time(),
                            "server": values,
                            "containers": containers,
                            "generator": stats.stdout.strip(),
                        }
                    )
                    + "\n"
                )
                resources.flush()
                if unsafe(values, args.max_job_backlog):
                    bad_since = bad_since or time.monotonic()
                    if time.monotonic() - bad_since >= 30:
                        raise ValueError("Unsafe production resource/telemetry window")
                else:
                    bad_since = None
                if (
                    time.time() - metadata["started_at"] > duration + 60
                    or sum(p.stat().st_size for p in output.iterdir()) > 2 * 1024**3
                ):
                    raise ValueError("Run deadline or output budget exceeded")
                time.sleep(5)
        metadata["exit_code"] = process.returncode
        metadata["deployment_after"] = deployment()
        if metadata["deployment_after"] != metadata["deployment_before"]:
            raise ValueError("Deployment or configuration changed during measurement")
        metadata["remote_write_series"] = query(
            args.prometheus_url,
            'count(count_over_time(k6_http_reqs_total{run_id="'
            + run_id
            + '",phase="business"}[5m]))',
        )
        if not (output / "summary.json").exists():
            raise ValueError("k6 produced no summary; inspect its private log")
        summary = json.loads((output / "summary.json").read_text())
        print(
            json.dumps(
                {
                    k: v
                    for k, v in summary["metrics"].items()
                    if "phase:business" in k or k in ["iterations", "dropped_iterations"]
                },
                indent=2,
            )
        )
        return process.returncode
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        metadata["aborted"] = True
        metadata["error_type"] = type(error).__name__
        if isinstance(error, ValueError):
            metadata["reason"] = str(error)
        raise
    finally:
        try:
            if process and process.poll() is None:
                subprocess.run(
                    ["docker", "stop", "--time", "10", container],
                    capture_output=True,
                    timeout=20,
                    check=False,
                )
                process.wait(timeout=10)
        finally:
            runtime.unlink(missing_ok=True)
            metadata["finished_at"] = time.time()
            (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")


if __name__ == "__main__":
    os.umask(0o077)
    try:
        raise SystemExit(main())
    except ValueError, OSError, KeyError, IndexError, subprocess.SubprocessError:
        raise SystemExit(
            "k6: preflight or safety check failed; inspect private evidence and fixture"
        ) from None
