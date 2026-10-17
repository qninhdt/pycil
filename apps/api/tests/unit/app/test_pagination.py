import base64
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from pycil.app.http import status_for
from pycil.app.pagination import decode, encode
from pycil.utils.errors import OperationError


def test_cursor_roundtrip_preserves_typed_seek_and_frozen_time():
    now, identifier = datetime(2026, 1, 1, tzinfo=UTC), uuid4()
    binding = {"viewer": "owner", "sort": "lemma_asc"}
    token = encode(binding, [now, identifier, "bank", 1, 0.5], as_of=now)
    assert decode(token, binding, ["time", "uuid", "text", "id", "rank"], timed=True) == (
        [now, identifier, "bank", 1, 0.5],
        now,
    )
    with pytest.raises(OperationError) as error:
        decode(
            token, binding | {"viewer": "other"}, ["time", "uuid", "text", "id", "rank"], timed=True
        )
    assert error.value.code == "invalid_cursor"


@pytest.mark.parametrize(
    "seek, kind",
    [
        ([True], "id"),
        ([0], "id"),
        (["2026-01-01T00:00:00"], "time"),
        ([True], "rank"),
        ([-1], "rank"),
        ([float("inf")], "rank"),
        ([float("nan")], "number"),
        (["x" * 513], "text"),
        ([123], "uuid"),
    ],
)
def test_untrusted_cursor_types_and_nonfinite_values_are_rejected(seek, kind):
    body = {"v": 1, "binding": {}, "seek": seek, "as_of": None}
    token = base64.urlsafe_b64encode(json.dumps(body).encode()).decode()
    with pytest.raises(OperationError) as error:
        decode(token, {}, [kind])
    assert error.value.code == "invalid_cursor"


@pytest.mark.parametrize("token", ["", "%%%", "e30", "W10", "bnVsbA", "x" * 2049])
def test_cursor_malformed_structures_are_safe_validation_errors(token):
    with pytest.raises(OperationError) as error:
        decode(token, {}, ["id"])
    assert status_for(error.value) == 422
