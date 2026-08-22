"""Parsers for CCDC GOLD configuration, ranking listings, and solution MOL2 files."""

from __future__ import annotations

import contextlib
import math
import re
from pathlib import Path
from typing import Any


def parse_gold_conf(file_path: Path) -> dict[str, Any]:
    """Parse gold.conf to extract target name, scoring functions, and parameters."""
    params: dict[str, str] = {}
    target_name: str | None = None
    fitness_func: str = "CHEMPLP"
    rescore_func: str | None = None

    content = file_path.read_text(encoding="utf-8", errors="replace")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line:
            parts = line.split("=", 1)
            key = parts[0].strip().lower()
            val = parts[1].strip()
            params[key] = val

            if key == "protein_datafile":
                p_path = Path(val)
                target_name = p_path.stem
            elif key == "fitness_function":
                fitness_func = val.upper()
            elif key == "rescore_function":
                rescore_func = val.upper()
        elif " " in line:
            parts = line.split(maxsplit=1)
            key = parts[0].strip().lower()
            val = parts[1].strip()
            params[key] = val

    if not target_name:
        target_name = file_path.parent.name or "gold_target"

    return {
        "target_name": target_name,
        "fitness_function": fitness_func,
        "rescore_function": rescore_func,
        "params": params,
    }


def _map_gold_score_key(header_name: str) -> str | None:
    """Map arbitrary GOLD score column name to canonical score key."""
    h = header_name.lower().strip()
    if "chemplp" in h or "plp" in h:
        return "gold.chemplp"
    if "goldscore" in h or (h.startswith("gold") and "score" in h):
        return "gold.goldscore"
    if "chemscore" in h:
        return "gold.chemscore"
    if "asp" in h:
        return "gold.asp"
    if "fitness" in h:
        return "gold.chemplp"
    return None


def parse_gold_ranking(file_path: Path) -> list[dict[str, Any]]:
    """Parse GOLD ranking file (bestranking.lst, gold_ranking.txt, ranking.csv)."""
    rows: list[dict[str, Any]] = []
    content = file_path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if not lines:
        return []

    first_non_comment = next(
        (ln for ln in lines if not ln.startswith("#")),
        None,
    )
    if not first_non_comment:
        return []

    delim = (
        "\t"
        if "\t" in first_non_comment
        else ("," if "," in first_non_comment else None)
    )

    headers: list[str] = []
    data_lines: list[str] = []

    for line in lines:
        if line.startswith("#"):
            stripped_comment = line.lstrip("#").strip()
            lower_comment = stripped_comment.lower()
            has_id_kw = any(k in lower_comment for k in ("rank", "solution", "file"))
            has_score_kw = any(
                k in lower_comment for k in ("fitness", "score", "chemplp", "ligand")
            )
            if has_id_kw and has_score_kw:
                if delim:
                    headers = [c.strip() for c in stripped_comment.split(delim)]
                else:
                    headers = [c.strip() for c in stripped_comment.split()]
            continue

        if not headers:
            if delim:
                headers = [c.strip() for c in line.split(delim)]
            else:
                headers = [c.strip() for c in line.split()]
            continue

        data_lines.append(line)

    for line in data_lines:
        tokens = (
            [c.strip() for c in line.split(delim)]
            if delim
            else [c.strip() for c in line.split()]
        )
        if not tokens:
            continue

        row_dict: dict[str, Any] = {
            "rank": 1,
            "solution_file": "",
            "ligand_name": "",
            "scores": {},
        }

        for idx, col in enumerate(headers):
            if idx >= len(tokens):
                break
            val = tokens[idx]
            col_lower = col.lower()

            if "rank" in col_lower:
                with contextlib.suppress(ValueError, TypeError):
                    row_dict["rank"] = int(val)
            elif "solution" in col_lower or "file" in col_lower:
                row_dict["solution_file"] = val
            elif any(k in col_lower for k in ("ligand", "name", "compound")):
                row_dict["ligand_name"] = val

            mapped_score = _map_gold_score_key(col)
            if mapped_score:
                try:
                    f_val = float(val)
                    if math.isfinite(f_val):
                        row_dict["scores"][mapped_score] = f_val
                except (ValueError, TypeError):
                    pass

        if not row_dict["ligand_name"] and row_dict["solution_file"]:
            soln_stem = Path(row_dict["solution_file"]).stem
            match = re.search(r"gold_soln_([^_]+)", soln_stem)
            row_dict["ligand_name"] = match.group(1) if match else soln_stem

        rows.append(row_dict)

    return rows


def parse_gold_mol2(file_path: Path) -> list[dict[str, Any]]:
    """Parse multi-molecule TRIPOS MOL2 file to extract poses and properties."""
    poses: list[dict[str, Any]] = []
    content = file_path.read_text(encoding="utf-8", errors="replace")

    chunks = content.split("@<TRIPOS>MOLECULE")
    for idx, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if not chunk:
            continue

        lines = chunk.splitlines()
        ligand_name = lines[0].strip() if lines else f"pose_{idx + 1}"

        atom_count = 0
        bond_count = 0
        if len(lines) > 1:
            counts = lines[1].split()
            if counts:
                with contextlib.suppress(ValueError, TypeError):
                    atom_count = int(counts[0])
                    bond_count = int(counts[1]) if len(counts) > 1 else 0

        scores: dict[str, float] = {}
        smiles: str | None = None
        for i, line in enumerate(lines):
            line_str = line.strip()
            if line_str.startswith("> <") and line_str.endswith(">"):
                prop_name = line_str[3:-1].strip()
                if prop_name.lower() in ("smiles", "canonical_smiles") and i + 1 < len(
                    lines
                ):
                    smiles = lines[i + 1].strip()
                score_key = _map_gold_score_key(prop_name)

                if score_key and i + 1 < len(lines):
                    val_str = lines[i + 1].strip()
                    try:
                        f_val = float(val_str)
                        if math.isfinite(f_val):
                            scores[score_key] = f_val
                    except (ValueError, TypeError):
                        pass

        poses.append(
            {
                "ligand_name": ligand_name,
                "smiles": smiles,
                "atom_count": atom_count,
                "bond_count": bond_count,
                "scores": scores,
                "raw_block": "@<TRIPOS>MOLECULE\n" + chunk,
            }
        )

    return poses


__all__ = [
    "parse_gold_conf",
    "parse_gold_mol2",
    "parse_gold_ranking",
]
