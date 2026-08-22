"""Smoke tests for packaging integrity, CLI subcommands, and SHA256 manifests."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import patch

import pytest

import fidelichem
from fidelichem.cli import create_parser, main
from fidelichem.exports.manifest import _compute_sha256


@pytest.mark.smoke
def test_package_metadata_and_version() -> None:
    assert hasattr(fidelichem, "__version__")
    assert fidelichem.__version__ == "0.1.0"


@pytest.mark.smoke
def test_cli_version_flag() -> None:
    parser = create_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--version"])
    assert exc_info.value.code == 0


@pytest.mark.smoke
def test_cli_export_subcommand(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_export"
    with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
        ret = main(["export", "--output", str(out_dir), "--formats", "csv,json"])
        assert ret == 0
        assert "Export completed" in mock_stdout.getvalue()
        assert (out_dir / "manifest.json").exists()


@pytest.mark.smoke
def test_compute_sha256_integrity(tmp_path: Path) -> None:
    test_file = tmp_path / "sample.txt"
    test_file.write_bytes(b"FideliChem reproducible build")
    sha, size = _compute_sha256(test_file)
    assert len(sha) == 64
    assert size == len(b"FideliChem reproducible build")
