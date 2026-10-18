"""Prometheus response contracts used by the release acceptance check."""

import json
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

SCRIPT = Path(__file__).resolve().parents[1] / "observe.py"


class ObserveTests(unittest.TestCase):
    def test_missing_stale_and_high_error_metrics_block_acceptance(self):
        values = []

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                query = parse_qs(urlsplit(self.path).query)["query"][0]
                if "timestamp(" in query:
                    value = values[0]
                elif "_sum{" in query:
                    value = values[3]
                elif "http_status_code" in query:
                    value = values[2]
                else:
                    value = values[1]
                result = [] if value is None else [{"value": [0, str(value)]}]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"status": "success", "data": {"result": result}}
                    ).encode()
                )

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for samples, passed in [
                ([10, 100, 0, 500], True),
                ([None, 100, 0, 500], False),
                ([100, 100, 0, 500], False),
                ([10, 100, 3, 500], False),
                ([10, 0, 0, 0], False),
            ]:
                with self.subTest(samples=samples):
                    values[:] = samples
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(SCRIPT),
                            f"http://127.0.0.1:{server.server_port}",
                            "test-release",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    self.assertEqual(result.returncode == 0, passed, result.stderr)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
