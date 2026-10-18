"""Exercise the release's HTTP checks against a real local HTTP server."""

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "smoke.py"


class SmokeTests(unittest.TestCase):
    def test_invalid_clerk_session_is_rejected_without_credentials_in_output(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / "runtime.env"
            session = Path(directory) / "session"
            env.write_text("CLERK_SECRET_KEY=test-only\n")
            session.write_text("../../invalid-session")
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT.parent / "session-token.py"),
                    str(env),
                    str(session),
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("test-only", result.stderr)
            self.assertNotIn("invalid-session", result.stderr)

    def test_readiness_search_and_auth_contracts(self):
        responses = {
            "/readyz": {"status": "ready"},
            "search": {"items": [{"kind": "reference"}]},
            "/v1/me": {"id": "00000000-0000-4000-8000-000000000001"},
        }

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.headers.get("User-Agent") != "pycil-deployment/1.0":
                    self.send_error(403)
                    return
                if (
                    self.path == "/v1/me"
                    and self.headers.get("Authorization") != "Bearer test-session"
                ):
                    self.send_error(401)
                    return
                self.send_response(200)
                self.end_headers()
                self.wfile.write(
                    json.dumps(responses.get(self.path, responses["search"])).encode()
                )

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for token, readiness, items, passed in [
                ("test-session", "ready", [{"kind": "reference"}], True),
                ("bad-session", "ready", [{"kind": "reference"}], False),
                ("test-session", "not_ready", [{"kind": "reference"}], False),
                ("test-session", "ready", [], False),
            ]:
                with self.subTest(token=token, readiness=readiness, items=items):
                    responses["/readyz"] = {"status": readiness}
                    responses["search"] = {"items": items}
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            f"http://127.0.0.1:{server.server_port}",
                            "authenticated",
                        ],
                        input=token,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=10,
                    )
                    self.assertEqual(result.returncode == 0, passed, result.stderr)
                    self.assertNotIn(token, result.stdout + result.stderr)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
