import re

import pytest

from pycil.account.handles import generate_handle

HEX_SUFFIX_PATTERN = re.compile(r"^[a-z0-9_]+_[0-9a-f]{8}$")


def test_generate_handle_standard_name():
    handle = generate_handle("Alice Smith")
    assert handle.startswith("alice_smith_")
    assert HEX_SUFFIX_PATTERN.match(handle)


def test_generate_handle_unicode_normalization():
    handle = generate_handle("Nguyễn Đắc Ninh")
    assert handle.startswith("nguyen_dac_ninh_")
    assert HEX_SUFFIX_PATTERN.match(handle)


@pytest.mark.parametrize(
    "display_name, expected_prefix",
    [
        ("", "user_"),
        ("   ", "user_"),
        ("!@#$%", "user_"),
        ("123", "user_123_"),
        ("123 numbers", "user_123_numbers_"),
        ("0test", "user_0test_"),
    ],
)
def test_generate_handle_prefixing_non_alpha(display_name, expected_prefix):
    handle = generate_handle(display_name)
    assert handle.startswith(expected_prefix)
    assert HEX_SUFFIX_PATTERN.match(handle)


def test_generate_handle_truncation_to_21_chars():
    long_name = "abcdefghijklmnopqrstuvwxyz"
    handle = generate_handle(long_name)
    prefix, suffix = handle.rsplit("_", 1)
    assert len(prefix) <= 21
    assert prefix == "abcdefghijklmnopqrstu"
    assert len(suffix) == 8
    assert len(handle) <= 30


def test_generate_handle_strips_trailing_underscores_before_suffix():
    # Construct a name whose 21st character falls on a delimiter/underscore
    name = "a" * 20 + " " + "b" * 10
    handle = generate_handle(name)
    prefix, suffix = handle.rsplit("_", 1)
    assert prefix == "a" * 20
    assert not prefix.endswith("_")
    assert "__" not in handle
    assert len(suffix) == 8


def test_generate_handle_hex_suffix_randomness():
    handles = {generate_handle("test_user") for _ in range(50)}
    assert len(handles) == 50
    for handle in handles:
        prefix, suffix = handle.rsplit("_", 1)
        assert prefix == "test_user"
        assert len(suffix) == 8
        assert all(c in "0123456789abcdef" for c in suffix)
