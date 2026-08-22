"""Unit tests for GROMACS analytical adapter."""

from __future__ import annotations

from pathlib import Path

from fidelichem.adapters.gromacs.adapter import GromacsAdapter


def test_gromacs_probe(tmp_path: Path) -> None:
    adapter = GromacsAdapter()
    assert adapter.probe(tmp_path).confidence == 0.0

    (tmp_path / "rmsd_backbone.xvg").write_text(
        """# GROMACS RMSD
@ title "RMSD"
@ xaxis label "Time (ns)"
@ yaxis label "RMSD (nm)"
@ s0 legend "Backbone"
0.0 0.01
1.0 0.15
""",
        encoding="utf-8",
    )

    report = adapter.probe(tmp_path)
    assert report.confidence >= 0.85
    assert report.suggested_adapter == "fidelichem.gromacs"


def test_gromacs_parse(tmp_path: Path) -> None:
    adapter = GromacsAdapter()
    (tmp_path / "rmsd.xvg").write_text(
        """@ title "RMSD"
@ xaxis label "Time (ns)"
@ yaxis label "RMSD (nm)"
@ s0 legend "Backbone"
0.0 0.05
1.0 0.12
2.0 0.18
""",
        encoding="utf-8",
    )
    (tmp_path / "rgyr.xvg").write_text(
        """@ title "Radius of Gyration"
@ xaxis label "Time (ns)"
@ yaxis label "Rg (nm)"
@ s0 legend "Protein"
0.0 1.45
1.0 1.46
2.0 1.44
""",
        encoding="utf-8",
    )

    plan = adapter.plan(tmp_path)
    bundle = adapter.parse(plan)

    assert len(bundle.md_metrics) == 2
    metric_keys = {m.metric_key for m in bundle.md_metrics}
    assert "rmsd" in metric_keys or "rmsd_backbone" in metric_keys
    assert "rgyr" in metric_keys or "radius_of_gyration" in metric_keys

    rmsd_m = next(m for m in bundle.md_metrics if "rmsd" in m.metric_key)
    assert rmsd_m.unit == "RMSD (nm)"
    assert rmsd_m.mean_value is not None
    assert rmsd_m.min_value == 0.05
    assert rmsd_m.max_value == 0.18

    val = adapter.validate(bundle)
    assert val.is_valid
