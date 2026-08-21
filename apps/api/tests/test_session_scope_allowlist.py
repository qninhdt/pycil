"""Sessions opened outside a request scope are on a written allowlist.

The DI standard is request-scoped `Depends(get_session)`: one transaction per
request, closed by the framework. `async_session_factory()` bypasses that, and an
unremarked bypass is how a codebase ends up with four coexisting session patterns
and no way to tell a deliberate exception from an accident.

Every site is therefore listed here with its reason. The test does not forbid the
pattern — some of these have no alternative — it forbids an *undocumented* use, so
a new one fails until somebody states why the request scope will not do.

The reasons, verified by reading each site:

* `db/session.py` — the definition of `get_session` itself.
* `assistant/application/tools.py` (12 sites) — LLM tool calls execute inside a LangGraph run,
  driven by the model rather than by the HTTP request. There is no request scope to
  inherit: the run outlives the response that started it.
* `assistant/application/run_service.py`, `assistant/application/hitl.py` — work that
  continues after the response has begun streaming: event persistence during a run,
  replay reads, and the action transitions that happen only as the body is consumed,
  so a client that never opens its stream cannot strand an action.
* `auth/dev_identity.py` — a development-only identity mint invoked outside the
  normal request path.
"""

import ast
import pathlib

import pytest

PYCIL = pathlib.Path(__file__).resolve().parents[1] / "pycil"

# Modules permitted to open their own session, with the reason recorded above.
# Deliberately a module allowlist rather than a line allowlist: line numbers move,
# and a stale line number would make this test fail for no real reason.
ALLOWED = {
    "db/session.py": "defines get_session",
    "assistant/application/tools.py": "LLM tool calls run outside any request scope",
    "assistant/application/run_service.py": "assistant runs continue after the response begins",
    "assistant/application/hitl.py": "human-in-the-loop resolution runs outside the request",
    "auth/dev_identity.py": "development-only identity mint, not a request path",
}


def _sites() -> dict[str, int]:
    """`{relative_path: count}` for every `async_session_factory()` call."""
    found: dict[str, int] = {}
    for source in sorted(PYCIL.rglob("*.py")):
        if "__pycache__" in str(source):
            continue
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        calls = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "async_session_factory"
        )
        if calls:
            found[source.relative_to(PYCIL).as_posix()] = calls
    return found


def test_every_self_opened_session_is_on_the_allowlist():
    """A new bypass fails here until its reason is written down."""
    unexplained = sorted(set(_sites()) - set(ALLOWED))
    assert not unexplained, (
        "these modules open their own session with no recorded reason: "
        f"{unexplained}. Either use Depends(get_session), or add the module to "
        "ALLOWED in this file with the reason the request scope will not do."
    )


def test_the_allowlist_has_no_stale_entries():
    """An entry whose module stopped bypassing should be removed, not left to rot.

    This is the direction the repo's two deleted import-linter contracts failed in:
    both named modules that no longer existed and still passed.
    """
    stale = sorted(set(ALLOWED) - set(_sites()))
    assert not stale, f"allowlist names modules that no longer self-open a session: {stale}"


@pytest.mark.parametrize("module", sorted(ALLOWED))
def test_each_allowlist_entry_carries_a_reason(module):
    assert ALLOWED[module].strip(), f"{module} is allowlisted with an empty reason"


def test_no_domain_router_outside_the_allowlist_opens_its_own_session():
    """Routers are the highest-risk case: a request scope is always available there.

    Called out separately from the general check because the failure is quiet — two
    sessions in one request means two transactions, so a later failure leaves the
    earlier write committed.
    """
    offenders = [
        path
        for path in _sites()
        if path.endswith("router.py") and path not in ALLOWED
    ]
    assert not offenders, f"routers opening their own session: {offenders}"
