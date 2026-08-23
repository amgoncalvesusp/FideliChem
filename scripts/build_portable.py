"""Build reproducible portable desktop artifacts for release workflows."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

_VERSION_PATTERN = re.compile(r"^(?:v)?(\d+\.\d+\.\d+)$")
_PLATFORMS = frozenset({"windows", "linux"})


def normalize_version(value: str) -> str:
    """Return a validated semantic release version without a leading ``v``."""

    match = _VERSION_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ValueError(
            "release version must be a semantic version, for example v0.1.0"
        )
    return match.group(1)


def artifact_name(version: str, platform: str) -> str:
    """Return the stable filename for a portable release artifact."""

    normalized = normalize_version(version)
    if platform not in _PLATFORMS:
        raise ValueError(f"unsupported release platform: {platform}")
    if platform == "windows":
        return f"FideliChem-{normalized}-Windows-x64.zip"
    return f"FideliChem-{normalized}-Linux-x64.tar.gz"


def pyinstaller_command(
    *,
    repo_root: Path,
    output_dir: Path,
    path_separator: str,
) -> list[str]:
    """Build the platform-neutral PyInstaller command used by CI."""

    asset_dir = repo_root / "src" / "fidelichem" / "gui" / "assets"
    icon_name = (
        "fidelichem-mark.ico" if path_separator == ";" else "fidelichem-mark.png"
    )
    icon_path = asset_dir / icon_name
    migration_dir = (
        repo_root / "src" / "fidelichem" / "storage" / "migrations"
    )
    return [
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "FideliChem",
        "--icon",
        str(icon_path),
        "--paths",
        str(repo_root / "src"),
        "--distpath",
        str(output_dir / "pyinstaller-dist"),
        "--workpath",
        str(output_dir / "pyinstaller-build"),
        "--specpath",
        str(output_dir / "pyinstaller-spec"),
        "--add-data",
        f"{asset_dir}{path_separator}fidelichem/gui/assets",
        "--add-data",
        f"{migration_dir}{path_separator}fidelichem/storage/migrations",
        "--collect-all",
        "rdkit",
        "scripts/launch_gui.py",
    ]


def _run_bundle_build(repo_root: Path, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    separator = ";" if os.name == "nt" else ":"
    command = [
        sys.executable,
        *pyinstaller_command(
            repo_root=repo_root,
            output_dir=output_dir,
            path_separator=separator,
        ),
    ]
    subprocess.run(command, cwd=repo_root, check=True)
    bundle_dir = output_dir / "pyinstaller-dist" / "FideliChem"
    if not bundle_dir.is_dir():
        raise RuntimeError("PyInstaller did not produce the FideliChem bundle")
    for notice_name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        notice = repo_root / notice_name
        if notice.is_file():
            shutil.copy2(notice, bundle_dir / notice.name)
    return bundle_dir


def _archive_windows(bundle_dir: Path, output_dir: Path, version: str) -> Path:
    target = output_dir / artifact_name(version, "windows")
    archive_base = target.with_suffix("").with_suffix("")
    archive = Path(
        shutil.make_archive(
            str(archive_base),
            "zip",
            root_dir=bundle_dir.parent,
            base_dir=bundle_dir.name,
        )
    )
    if archive != target:
        archive.replace(target)
    return target


def _archive_linux(bundle_dir: Path, output_dir: Path, version: str) -> Path:
    target = output_dir / artifact_name(version, "linux")
    with tarfile.open(target, "w:gz") as archive:
        archive.add(bundle_dir, arcname="FideliChem")
    return target


def _build_deb(
    *,
    repo_root: Path,
    bundle_dir: Path,
    output_dir: Path,
    version: str,
) -> Path:
    dpkg_deb = shutil.which("dpkg-deb")
    if dpkg_deb is None:
        raise RuntimeError("dpkg-deb is required to build the Linux installer")

    package_name = f"FideliChem-{version}-Linux-x64.deb"
    with tempfile.TemporaryDirectory(prefix="fidelichem-deb-") as temporary:
        root = Path(temporary) / f"fidelichem_{version}_amd64"
        opt_dir = root / "opt" / "fidelichem"
        (root / "DEBIAN").mkdir(parents=True)
        opt_dir.parent.mkdir(parents=True)
        shutil.copytree(bundle_dir, opt_dir / "FideliChem")

        control = "\n".join(
            (
                "Package: fidelichem",
                f"Version: {version}",
                "Section: science",
                "Priority: optional",
                "Architecture: amd64",
                "Maintainer: FideliChem contributors",
                "Description: Explainable molecular evidence workspace",
                " Portable PySide6 desktop application for audited evidence.",
                "Depends: libglib2.0-0, libx11-6, libxkbcommon-x11-0",
                "",
            )
        )
        (root / "DEBIAN" / "control").write_text(control, encoding="utf-8")

        launcher_dir = root / "usr" / "bin"
        launcher_dir.mkdir(parents=True)
        launcher = launcher_dir / "fidelichem-gui"
        launcher.write_text(
            "#!/bin/sh\nexec /opt/fidelichem/FideliChem/FideliChem \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)

        icon_dir = root / "usr" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        icon_dir.mkdir(parents=True)
        shutil.copy2(
            repo_root
            / "src"
            / "fidelichem"
            / "gui"
            / "assets"
            / "fidelichem-mark.svg",
            icon_dir / "fidelichem.svg",
        )
        desktop_dir = root / "usr" / "share" / "applications"
        desktop_dir.mkdir(parents=True)
        (desktop_dir / "fidelichem.desktop").write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=FideliChem\n"
            "Comment=Explainable molecular evidence workspace\n"
            "Exec=fidelichem-gui\n"
            "Icon=fidelichem\n"
            "Categories=Science;Chemistry;\n",
            encoding="utf-8",
        )

        target = output_dir / package_name
        subprocess.run([dpkg_deb, "--build", str(root), str(target)], check=True)
        return target


def build_release_artifacts(
    *,
    repo_root: Path,
    output_dir: Path,
    version: str,
    platform: str,
) -> tuple[Path, ...]:
    """Build the portable archive and, on Linux, a native Debian package."""

    normalized = normalize_version(version)
    if platform not in _PLATFORMS:
        raise ValueError(f"unsupported release platform: {platform}")
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = _run_bundle_build(repo_root, output_dir)
    if platform == "windows":
        return (_archive_windows(bundle_dir, output_dir, normalized),)
    return (
        _archive_linux(bundle_dir, output_dir, normalized),
        _build_deb(
            repo_root=repo_root,
            bundle_dir=bundle_dir,
            output_dir=output_dir,
            version=normalized,
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", choices=sorted(_PLATFORMS), required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parent.parent
    artifacts = build_release_artifacts(
        repo_root=repo_root,
        output_dir=args.output_dir,
        version=args.version,
        platform=args.platform,
    )
    for artifact in artifacts:
        print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
