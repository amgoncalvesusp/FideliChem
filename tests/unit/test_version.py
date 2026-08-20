import re
from importlib.metadata import version

import pytest

from fidelichem import __version__


@pytest.mark.unit
def test_public_version_is_semantic_and_matches_package_metadata() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)
    assert __version__ == version("fidelichem")
