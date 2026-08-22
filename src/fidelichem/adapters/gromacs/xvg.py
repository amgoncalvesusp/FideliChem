"""Robust parser for GROMACS/Grace XVG analytical curve files."""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class XVGData:
    """Structured analytical time series parsed from a GROMACS XVG file."""

    title: str
    xaxis_label: str
    yaxis_label: str
    series_legends: tuple[str, ...]
    time_points: tuple[float, ...]
    series_values: tuple[tuple[float, ...], ...]
    series_summaries: tuple[dict[str, float], ...]


_CONTROL_STR_RE = re.compile(r'@\s+([a-zA-Z0-9_\s]+?)\s+"(.*)"')
_LEGEND_RE = re.compile(r'@\s+s(\d+)\s+legend\s+"(.*)"')


def parse_xvg(source: Path | str) -> XVGData:
    """Parse GROMACS XVG file preserving legends, metadata, and multi-series curves."""
    text = (
        Path(source).read_text(encoding="utf-8", errors="replace")
        if isinstance(source, Path) or (isinstance(source, str) and "\n" not in source)
        else str(source)
    )

    title = ""
    xaxis_label = ""
    yaxis_label = ""
    legends_dict: dict[int, str] = {}

    time_points_list: list[float] = []
    raw_series_values: list[list[float]] = []

    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue

        if line_clean.startswith("@"):
            leg_m = _LEGEND_RE.match(line_clean)
            if leg_m:
                s_idx = int(leg_m.group(1))
                legends_dict[s_idx] = leg_m.group(2).strip()
                continue

            ctrl_m = _CONTROL_STR_RE.match(line_clean)
            if ctrl_m:
                key = ctrl_m.group(1).lower().replace(" ", "")
                val = ctrl_m.group(2).strip()
                if "title" in key:
                    title = val
                elif "xaxis" in key:
                    xaxis_label = val
                elif "yaxis" in key:
                    yaxis_label = val
            continue

        # Data row
        tokens = line_clean.split()
        if not tokens:
            continue
        try:
            t_val = float(tokens[0])
            y_vals = [float(tok) for tok in tokens[1:]]
        except ValueError:
            continue

        if not raw_series_values:
            for _ in range(len(y_vals)):
                raw_series_values.append([])

        time_points_list.append(t_val)
        for s_idx, y_val in enumerate(y_vals):
            if s_idx < len(raw_series_values):
                raw_series_values[s_idx].append(y_val)

    num_series = len(raw_series_values)
    series_legends_list: list[str] = []
    for s_idx in range(num_series):
        series_legends_list.append(legends_dict.get(s_idx, f"Series_{s_idx + 1}"))

    summaries_list: list[dict[str, float]] = []
    for series in raw_series_values:
        finite_vals = [v for v in series if math.isfinite(v)]
        if finite_vals:
            summaries_list.append(
                {
                    "count": float(len(finite_vals)),
                    "min": min(finite_vals),
                    "max": max(finite_vals),
                    "mean": statistics.mean(finite_vals),
                    "std": (
                        statistics.stdev(finite_vals) if len(finite_vals) > 1 else 0.0
                    ),
                }
            )
        else:
            summaries_list.append(
                {"count": 0.0, "min": 0.0, "max": 0.0, "mean": 0.0, "std": 0.0}
            )

    return XVGData(
        title=title,
        xaxis_label=xaxis_label,
        yaxis_label=yaxis_label,
        series_legends=tuple(series_legends_list),
        time_points=tuple(time_points_list),
        series_values=tuple(tuple(s) for s in raw_series_values),
        series_summaries=tuple(summaries_list),
    )


__all__ = ["XVGData", "parse_xvg"]
