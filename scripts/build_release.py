"""Release packaging script building source distributions, wheels, and SHA256SUMS."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


def compute_sha256(path: Path) -> str:
    """Calculate SHA-256 digest for a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_release_packages(dist_dir: Path) -> list[Path]:
    """Build wheel and sdist packages and generate SHA256SUMS.txt."""
    dist_dir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, "-m", "build", "--outdir", str(dist_dir)]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except Exception:
        subprocess.run(["uv", "build", "--out-dir", str(dist_dir)], check=True)

    artifacts = [
        p
        for p in dist_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.name != "SHA256SUMS.txt"
    ]

    sums_path = dist_dir / "SHA256SUMS.txt"
    lines = []
    for art in sorted(artifacts):
        sha = compute_sha256(art)
        lines.append(f"{sha}  {art.name}")

    sums_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return artifacts


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    dist_dir = repo_root / "dist"
    print(f"Building release artifacts in {dist_dir}...")
    artifacts = build_release_packages(dist_dir)
    for art in artifacts:
        print(f"  Created: {art.name}")
    print("  Generated: SHA256SUMS.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
