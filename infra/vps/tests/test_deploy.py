"""Check sequential worker replacement without starting deployment infrastructure."""

import subprocess
import unittest
from pathlib import Path


class WorkerReplacementTests(unittest.TestCase):
    def test_each_worker_must_start_before_the_next_replacement(self):
        source = (Path(__file__).resolve().parents[1] / "deploy.sh").read_text()
        function = source[source.index("start_worker() {") : source.index("\nmanifest() {")]
        for failed, expected, status in [
            ("", "worker\nworker-2\n", 0),
            ("worker", "worker\n", 1),
            ("worker-2", "worker\nworker-2\n", 1),
            ("worker-startup", "worker\n", 1),
            ("worker-2-startup", "worker\nworker-2\n", 1),
            ("worker-dead", "worker\n", 1),
        ]:
            with self.subTest(failed=failed):
                result = subprocess.run(
                    [
                        "bash",
                        "-c",
                        function
                        + r"""
failed=$1
run() {
  if [[ "$1" = up ]]; then
    service=${!#}
    echo "$service"
    [[ "$service" != "$failed" ]]
  else
    echo "${!#}"
  fi
}
docker() {
  if [[ "$1" = logs ]]; then
    [[ "$failed" = "${!#}-startup" ]] || echo 'Listening started.'
  elif [[ "$*" = *State.Running* ]]; then
    if [[ "$failed" = "${!#}-dead" ]]; then echo 'false started'
    else echo 'true started'; fi
  else echo started
  fi
}
sleep() { :; }
start_worker
""",
                        "test",
                        failed,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                self.assertEqual(result.returncode, status, result.stderr)
                self.assertEqual(result.stdout, expected)
