import subprocess
import sys

import pytest

from fidelichem import __version__
from fidelichem.cli import main


def run_module(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "fidelichem", *arguments],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )


@pytest.mark.integration
def test_main_without_arguments_returns_success() -> None:
    assert main([]) == 0


@pytest.mark.integration
def test_module_version_reports_package_version() -> None:
    result = run_module("--version")

    assert result.returncode == 0
    assert result.stdout == f"fidelichem {__version__}\n"
    assert result.stderr == ""


@pytest.mark.integration
def test_module_help_is_successful() -> None:
    result = run_module("--help")

    assert result.returncode == 0
    assert "usage: fidelichem" in result.stdout
    assert result.stderr == ""


@pytest.mark.integration
def test_module_rejects_unknown_arguments() -> None:
    result = run_module("--unknown")

    assert result.returncode == 2
    assert result.stdout == ""
    assert "unrecognized arguments: --unknown" in result.stderr
