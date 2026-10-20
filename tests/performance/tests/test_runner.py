"""Safety checks without starting Docker or making network requests."""

import base64
import importlib.util
import json
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "run_k6", Path(__file__).resolve().parents[3] / "scripts/run-k6.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SafetyTests(unittest.TestCase):
    def test_each_resource_limit_can_stop_the_run(self):
        healthy = {
            "available_memory_ratio": 0.7,
            "disk_available_bytes": 40 * 1024**3,
            "disk_time_to_full": 30 * 1024**3,
            "container_memory_ratio": 0.5,
            "wal_backlog_seconds": 0,
            "telemetry_age_seconds": 10,
            "telemetry_missing": 0,
            "job_backlog": 0,
        }
        self.assertFalse(runner.unsafe(healthy))
        self.assertFalse(runner.unsafe({**healthy, "job_backlog": 8}, max_job_backlog=8))
        self.assertTrue(runner.unsafe({**healthy, "job_backlog": 9}, max_job_backlog=8))
        self.assertTrue(
            runner.unsafe(
                {**healthy, "job_backlog": 8, "container_memory_ratio": 0.91},
                max_job_backlog=8,
            )
        )
        for key, bad in {
            "available_memory_ratio": 0.1,
            "disk_available_bytes": 1,
            "disk_time_to_full": -1,
            "container_memory_ratio": 0.91,
            "wal_backlog_seconds": 301,
            "telemetry_age_seconds": 91,
            "telemetry_missing": 1,
            "job_backlog": 1,
        }.items():
            with self.subTest(key=key):
                self.assertTrue(runner.unsafe({**healthy, key: bad}))

    def test_rejects_wrong_issuer_short_lifetime_and_forged_fixture_expiry(self):
        expiry = int(time.time()) + 3600
        claims = {"iss": "https://clerk.example.com", "sub": "test", "exp": expiry}
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
        user = {
            "token": "header." + payload + ".signature",
            "expires_at": datetime.fromtimestamp(expiry, UTC).isoformat(),
        }
        fixture = {"users": [user]}
        runner.validate_tokens(fixture, claims["iss"], expiry - 300)
        for issuer, minimum in [
            ("https://wrong.example.com", expiry - 300),
            (claims["iss"], expiry + 1),
        ]:
            with self.assertRaises(ValueError):
                runner.validate_tokens(fixture, issuer, minimum)
        with self.assertRaises(ValueError):
            runner.validate_tokens(
                {"users": [{**user, "expires_at": "2099-01-01T00:00:00Z"}]},
                claims["iss"],
                expiry - 300,
            )


if __name__ == "__main__":
    unittest.main()
