"""Unit tests for GROMACS XVG parser supporting single and multi-series curves."""

from __future__ import annotations

from pathlib import Path

from fidelichem.adapters.gromacs.xvg import parse_xvg


def test_parse_single_series_xvg(tmp_path: Path) -> None:
    xvg_file = tmp_path / "rmsd.xvg"
    xvg_file.write_text(
        """# This is a GROMACS XVG file
# Produced by gmx rms
@    title "RMSD"
@    xaxis  label "Time (ps)"
@    yaxis  label "RMSD (nm)"
@TYPE xy
@ view 0.15, 0.15, 0.75, 0.85
@ legend on
@ legend box on
@ s0 legend "Backbone"
   0.0000000    0.0000492
  10.0000000    0.1245000
  20.0000000    0.1862000
  30.0000000    0.2014000
""",
        encoding="utf-8",
    )

    data = parse_xvg(xvg_file)
    assert data.title == "RMSD"
    assert data.xaxis_label == "Time (ps)"
    assert data.yaxis_label == "RMSD (nm)"
    assert data.series_legends == ("Backbone",)
    assert len(data.time_points) == 4
    assert len(data.series_values[0]) == 4
    assert data.time_points[0] == 0.0
    assert data.time_points[-1] == 30.0

    summary = data.series_summaries[0]
    assert summary["min"] == 0.0000492
    assert summary["max"] == 0.2014000
    assert summary["mean"] > 0.1


def test_parse_multi_series_xvg(tmp_path: Path) -> None:
    xvg_file = tmp_path / "rmsd_multi.xvg"
    xvg_file.write_text(
        """# Multi-series RMSD
@    title "RMSD Protein & Ligand"
@    xaxis  label "Time (ns)"
@    yaxis  label "RMSD (nm)"
@ s0 legend "Protein Backbone"
@ s1 legend "Ligand Heavy Atoms"
   0.000    0.001    0.002
   1.000    0.150    0.210
   2.000    0.180    0.260
""",
        encoding="utf-8",
    )

    data = parse_xvg(xvg_file)
    assert data.title == "RMSD Protein & Ligand"
    assert data.series_legends == ("Protein Backbone", "Ligand Heavy Atoms")
    assert len(data.series_values) == 2
    assert len(data.series_values[0]) == 3
    assert len(data.series_values[1]) == 3

    assert data.series_summaries[0]["max"] == 0.180
    assert data.series_summaries[1]["max"] == 0.260
