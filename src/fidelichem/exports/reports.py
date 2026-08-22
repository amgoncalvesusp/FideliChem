"""Scientific methods and reproducibility report generator."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import fidelichem


def generate_methods_report(
    project_name: str,
    parameters: Mapping[str, Any],
    output_path: Path,
) -> Path:
    """Generate a structured Markdown methods report for audit and reproducibility."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    version = getattr(fidelichem, "__version__", "0.1.0")

    lines = [
        "# FideliChem — Methods & Reproducibility Report",
        f"**Project:** {project_name}  ",
        f"**Generated:** {timestamp}  ",
        f"**FideliChem Version:** {version}  ",
        "",
        "## 1. Computational Pipeline & Workflow",
        (
            "This project executed multi-fidelity cheminformatics, "
            "docking triage, interaction consensus, and MD analytics "
            "under strict data immutability and provenance tracking."
        ),
        "",
        "## 2. Parameterization & Scientific Criteria",
        (
            "The following parameters governed normalization, consensus "
            "evaluation, and decision triage:"
        ),
        "",
    ]

    for k, v in sorted(parameters.items()):
        lines.append(f"- **`{k}`**: {v}")

    lines.extend(
        [
            "",
            "## 3. Data Integrity & Reproducibility",
            "- All raw input files are cryptographically fingerprinted using SHA-256.",
            (
                "- Normalization preserves missing observations (`None`) "
                "non-destructively without silent zero-imputation."
            ),
            (
                "- In-pocket 3D pose RMSD evaluates chemical symmetry via "
                "topological automorphism matching."
            ),
            (
                "- Decision priorities are supported by explicit justifications "
                "(`why_positive`, `why_negative`, and warnings)."
            ),
            "",
            "---",
            f"*Generated autonomously by FideliChem v{version}*",
        ]
    )

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


__all__ = ["generate_methods_report"]
