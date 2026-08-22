"""Unit tests for Table Importer domain models and mapping schemas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fidelichem.domain.table_importer import (
    IdentityColumnMapping,
    ScoreColumnMapping,
    ScoreDirection,
    ScoreScope,
    TableMappingPreset,
    TableMappingSchema,
)


def test_score_column_mapping_validation() -> None:
    mapping = ScoreColumnMapping(
        column_name="chemplp_score",
        score_key="gold.chemplp",
        direction=ScoreDirection.HIGHER_BETTER,
        unit="arbitrary",
        scope=ScoreScope.RUN,
        description="GOLD ChemPLP fitness",
    )
    assert mapping.column_name == "chemplp_score"
    assert mapping.score_key == "gold.chemplp"
    assert mapping.direction == ScoreDirection.HIGHER_BETTER
    assert mapping.scope == ScoreScope.RUN

    with pytest.raises(ValidationError, match="column_name"):
        ScoreColumnMapping(column_name="", score_key="key")

    with pytest.raises(ValidationError, match="score_key"):
        ScoreColumnMapping(column_name="col", score_key="  ")


def test_identity_column_mapping_validation() -> None:
    mapping = IdentityColumnMapping(
        molecule_id_column="Compound_ID",
        smiles_column="SMILES",
        source_system_default="in_house_screening",
        target_name_default="Target_A",
        run_name_default="Screen_Run_1",
        pose_id_column="Pose",
        rank_column="Rank",
    )
    assert mapping.molecule_id_column == "Compound_ID"
    assert mapping.smiles_column == "SMILES"
    assert mapping.source_system_default == "in_house_screening"

    # Default fallback values
    default_mapping = IdentityColumnMapping()
    assert default_mapping.source_system_default == "table_import"
    assert default_mapping.run_name_default == "default_run"


def test_table_mapping_schema_serialization() -> None:
    score1 = ScoreColumnMapping(
        column_name="affinity",
        score_key="docking.affinity",
        direction=ScoreDirection.LOWER_BETTER,
    )
    identity = IdentityColumnMapping(
        molecule_id_column="id",
        smiles_column="smiles",
    )
    schema = TableMappingSchema(
        identity=identity,
        scores=(score1,),
        property_columns=("mw", "logp"),
        metadata_columns=("vendor",),
        delimiter=",",
        has_header=True,
    )

    data = schema.model_dump(mode="json")
    restored = TableMappingSchema.model_validate(data)
    assert restored.identity.molecule_id_column == "id"
    assert len(restored.scores) == 1
    assert restored.scores[0].score_key == "docking.affinity"
    assert restored.property_columns == ("mw", "logp")
    assert restored.delimiter == ","


def test_table_mapping_preset_lifecycle() -> None:
    now = datetime(2026, 8, 22, 12, 0, 0, tzinfo=UTC)
    identity = IdentityColumnMapping(
        molecule_id_column="ligand_name",
        smiles_column="canonical_smiles",
    )
    schema = TableMappingSchema(
        identity=identity,
        scores=(
            ScoreColumnMapping(
                column_name="score",
                score_key="vina.score",
                direction=ScoreDirection.LOWER_BETTER,
            ),
        ),
    )
    preset = TableMappingPreset(
        name="Vina Default Output",
        description="Preset for AutoDock Vina CSV tables",
        schema_definition=schema,
        created_at=now,
        updated_at=now,
    )

    assert preset.name == "Vina Default Output"
    assert preset.id is not None
    assert preset.created_at == now
    assert len(preset.schema_definition.scores) == 1

    dumped = preset.model_dump(mode="json")
    loaded = TableMappingPreset.model_validate(dumped)
    assert loaded.id == preset.id
    assert loaded.name == preset.name
    assert loaded.schema_definition.scores[0].score_key == "vina.score"
