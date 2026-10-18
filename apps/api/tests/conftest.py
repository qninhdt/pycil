"""Shared fixtures; unit tests never request container infrastructure."""

from typing import Any

pytest_plugins = ["tests.support.containers", "tests.support.telemetry"]

_cov: Any = None


def pytest_configure_node(node: Any) -> None:
    try:
        import coverage

        if coverage.Coverage.current() is not None:
            node.workerinput["coverage_active"] = True
    except ImportError:
        pass


def pytest_configure(config: Any) -> None:
    global _cov
    workerinput = getattr(config, "workerinput", None)
    if workerinput and workerinput.get("coverage_active"):
        try:
            import coverage

            _cov = coverage.Coverage()
            _cov.start()
        except ImportError:
            pass


def pytest_unconfigure(config: Any) -> None:
    global _cov
    if _cov is not None:
        _cov.stop()
        _cov.save()
        _cov = None
