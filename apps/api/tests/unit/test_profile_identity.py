import re

import pytest
from pydantic import ValidationError

from pycil.account.handles import generate_handle
from pycil.account.schemas import ProfilePatch


@pytest.mark.parametrize("name", ["Nguyễn Đình Ninh", "李明", "😊", "123", "A", "a" * 255])
def test_generated_handles_are_valid_and_distinct(name):
    handles = [generate_handle(name) for _ in range(3)]
    assert all(re.fullmatch(r"[a-z][a-z0-9_]{2,29}", handle) for handle in handles)
    assert len(set(handles)) == 3
    if name == "Nguyễn Đình Ninh":
        assert all(handle.startswith("nguyen_dinh_ninh_") for handle in handles)


def test_profile_patch_preserves_omission_and_trims_display_name():
    assert ProfilePatch(bio=None).model_dump(exclude_unset=True) == {"bio": None}
    assert ProfilePatch(display_name=" Nguyễn Ninh ").display_name == "Nguyễn Ninh"
    for value in (None, "", " \n ", "a" * 256):
        with pytest.raises(ValidationError):
            ProfilePatch(display_name=value)
