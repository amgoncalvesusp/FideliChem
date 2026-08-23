from pathlib import Path

import pytest

from scripts.build_portable import (
    artifact_name,
    normalize_version,
    pyinstaller_command,
)


def test_normalize_release_version_accepts_tag_and_rejects_untrusted_input() -> None:
    assert normalize_version("v0.1.0") == "0.1.0"
    assert normalize_version("0.1.0") == "0.1.0"

    with pytest.raises(ValueError, match="semantic version"):
        normalize_version("v0.1/../../main")


def test_release_artifact_names_are_stable() -> None:
    assert artifact_name("v0.1.0", "windows") == (
        "FideliChem-0.1.0-Windows-x64.zip"
    )
    assert artifact_name("v0.1.0", "linux") == (
        "FideliChem-0.1.0-Linux-x64.tar.gz"
    )


def test_pyinstaller_command_bundles_runtime_assets(tmp_path: Path) -> None:
    command = pyinstaller_command(
        repo_root=tmp_path,
        output_dir=tmp_path / "release",
        path_separator=":",
    )

    assert command[:3] == ["-m", "PyInstaller", "--noconfirm"]
    assert "--windowed" in command
    assert "--icon" in command
    assert any(value.endswith("fidelichem-mark.png") for value in command)
    assert "--collect-all" in command
    data_args = [value for value in command if "fidelichem/" in value]
    assert any("fidelichem/gui/assets" in value for value in data_args)
    assert any("fidelichem/storage/migrations" in value for value in data_args)


def test_windows_pyinstaller_command_uses_ico_artwork(tmp_path: Path) -> None:
    command = pyinstaller_command(
        repo_root=tmp_path,
        output_dir=tmp_path / "release",
        path_separator=";",
    )

    assert any(value.endswith("fidelichem-mark.ico") for value in command)
