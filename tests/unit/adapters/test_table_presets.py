"""Unit tests for Table Importer PresetManager."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fidelichem.adapters.table.presets import PresetManager
from fidelichem.domain.table_importer import (
    IdentityColumnMapping,
    ScoreColumnMapping,
    ScoreDirection,
    TableMappingPreset,
    TableMappingSchema,
)


def _sample_preset() -> TableMappingPreset:
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    identity = IdentityColumnMapping(
        molecule_id_column="Compound_Name",
        smiles_column="SMILES_canonical",
        target_name_default="Target_X",
    )
    scores = (
        ScoreColumnMapping(
            column_name="ChemPLP",
            score_key="gold.chemplp",
            direction=ScoreDirection.HIGHER_BETTER,
        ),
        ScoreColumnMapping(
            column_name="GoldScore",
            score_key="gold.goldscore",
            direction=ScoreDirection.HIGHER_BETTER,
        ),
    )
    schema = TableMappingSchema(identity=identity, scores=scores, delimiter=",")
    return TableMappingPreset(
        name="GOLD Lab Export",
        description="Standard GOLD CSV format for Lab 1",
        schema_definition=schema,
        created_at=now,
        updated_at=now,
    )


def test_preset_save_and_load(tmp_path: Path) -> None:
    manager = PresetManager()
    preset = _sample_preset()

    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()

    saved_path = manager.save_preset(preset, preset_dir)
    assert saved_path.exists()
    assert saved_path.suffix == ".json"

    loaded = manager.load_preset(saved_path)
    assert loaded.id == preset.id
    assert loaded.name == preset.name
    assert loaded.schema_definition.identity.molecule_id_column == "Compound_Name"
    assert len(loaded.schema_definition.scores) == 2


def test_preset_list_and_match(tmp_path: Path) -> None:
    manager = PresetManager()
    preset1 = _sample_preset()

    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    preset2 = TableMappingPreset(
        name="Vina Simple",
        schema_definition=TableMappingSchema(
            identity=IdentityColumnMapping(
                molecule_id_column="Ligand",
                smiles_column="Structure",
            ),
            scores=(
                ScoreColumnMapping(
                    column_name="Affinity",
                    score_key="vina.affinity",
                    direction=ScoreDirection.LOWER_BETTER,
                ),
            ),
        ),
        created_at=now,
        updated_at=now,
    )

    preset_dir = tmp_path / "presets"
    preset_dir.mkdir()

    manager.save_preset(preset1, preset_dir)
    manager.save_preset(preset2, preset_dir)

    all_presets = manager.list_presets(preset_dir)
    assert len(all_presets) == 2
    names = {p.name for p in all_presets}
    assert names == {"GOLD Lab Export", "Vina Simple"}

    # Match against GOLD table headers
    gold_headers = [
        "Compound_Name",
        "SMILES_canonical",
        "ChemPLP",
        "GoldScore",
        "UnrelatedCol",
    ]
    matches = manager.match_preset(gold_headers, all_presets)
    assert len(matches) == 2
    # First match should be GOLD Lab Export with 1.0 (all 4 mapped columns found)
    best_preset, score = matches[0]
    assert best_preset.name == "GOLD Lab Export"
    assert score == 1.0
