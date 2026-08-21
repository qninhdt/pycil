"""The broker port, its adapter, and its fake agree on one surface.

A Protocol is documentation until something compares it to the class that claims
to satisfy it. Nothing does that at runtime: `RealtimeControl` is not
`@runtime_checkable`, no type checker runs in CI on this package, and a missing
method surfaces as an `AttributeError` on a logout — after the account rows are
already gone.

So this is the check. It reads the Protocol's own annotations rather than a
hand-kept list of names, which is what stops it rotting the way this repo's
earlier hand-listed contracts did: adding a method to the port automatically
extends what the adapter and the fake must provide.

The fake is included deliberately. A fake that drifts from the adapter passes
every test that uses it while proving nothing about production.
"""

import inspect

from pycil.ports.centrifugo import CentrifugoControl, RealtimeControl
from tests.realtime.fakes import FakeRealtimeControl

_IMPLEMENTATIONS = (CentrifugoControl, FakeRealtimeControl)


def _port_methods() -> set[str]:
    return {
        name
        for name, value in vars(RealtimeControl).items()
        if callable(value) and not name.startswith("_")
    }


def test_the_port_declares_the_methods_pycil_actually_calls():
    """A guard on the guard: an empty port would make every check below vacuous."""
    assert _port_methods() == {
        "readiness",
        "mint_connection_token",
        "disconnect_user",
        "publish",
    }


def test_every_implementation_provides_the_whole_port():
    expected = _port_methods()
    for implementation in _IMPLEMENTATIONS:
        missing = {name for name in expected if not hasattr(implementation, name)}
        assert not missing, f"{implementation.__name__} is missing {sorted(missing)}"


def test_signatures_match_the_port():
    """Same parameter names, in the same order.

    Callers pass `token_version` positionally in one place and by keyword in
    another, so a renamed parameter is a runtime break that "the method exists"
    would not catch.
    """
    for name in _port_methods():
        expected = list(inspect.signature(getattr(RealtimeControl, name)).parameters)
        for implementation in _IMPLEMENTATIONS:
            actual = list(inspect.signature(getattr(implementation, name)).parameters)
            assert actual == expected, (
                f"{implementation.__name__}.{name}{tuple(actual)} does not match "
                f"the port's {tuple(expected)}"
            )


def test_asyncness_matches_the_port():
    """`mint_connection_token` is sync on purpose — it signs locally, no I/O.

    Getting this wrong in one direction returns an un-awaited coroutine as a token;
    in the other it awaits a plain tuple. Both are runtime failures on the realtime
    handshake, and neither is a missing method.
    """
    for name in _port_methods():
        expected = inspect.iscoroutinefunction(getattr(RealtimeControl, name))
        for implementation in _IMPLEMENTATIONS:
            actual = inspect.iscoroutinefunction(getattr(implementation, name))
            assert actual == expected, (
                f"{implementation.__name__}.{name} async={actual}, port async={expected}"
            )


def test_the_adapter_exposes_no_extra_public_surface():
    """Anything public beyond the port is something a consumer could couple to.

    `close` is the one sanctioned addition: the shared client has to be released at
    shutdown, and that is lifecycle rather than broker capability, so it stays off
    the port that routers depend on.
    """
    public = {
        name
        for name in vars(CentrifugoControl)
        if not name.startswith("_") and callable(getattr(CentrifugoControl, name))
    }
    assert public - _port_methods() == {"close"}
