import pytest

from pycil.themes.errors import InvalidThemeError
from pycil.themes.namespace import normalize_key


def test_theme_key_has_exact_casefolded_whitespace_identity():
    assert normalize_key("  Space   CREW ") == "space crew"
    assert normalize_key("Straße") == "strasse"


@pytest.mark.parametrize("value", ["", " ", None, 123, "x" * 256])
def test_empty_and_invalid_theme_keys_are_rejected(value):
    with pytest.raises(InvalidThemeError):
        normalize_key(value)
