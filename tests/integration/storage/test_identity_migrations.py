from __future__ import annotations

# Direct SQL fixtures intentionally mirror the migration's column expressions.
# ruff: noqa: E501
from collections.abc import Generator
from pathlib import Path
from threading import Barrier, Thread

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from fidelichem.storage.engine import create_sqlite_engine
from fidelichem.storage.runner import current_revision, upgrade_database

PROJECT = "11111111-1111-4111-8111-111111111111"
BATCH = "33333333-3333-4333-8333-333333333333"
ARTIFACT = "55555555-5555-4555-8555-555555555555"
AUDIT = "44444444-4444-4444-8444-444444444444"
COMPOUND = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
COMPOUND_2 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
STATE = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
ALIAS = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ALIAS_2 = "abababab-abab-4aba-8aba-abababababab"
ROOT = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
NEXT = "ffffffff-ffff-4fff-8fff-ffffffffffff"
RACE_A = "15151515-1515-4151-8151-151515151515"
RACE_B = "16161616-1616-4161-8161-161616161616"
RETRACT = "12121212-1212-4121-8121-121212121212"
RESTORE = "13131313-1313-4131-8131-131313131313"
RETRACT_AGAIN = "14141414-1414-4141-8141-141414141414"
STAMP = "2026-01-01T00:00:00.000000Z"
HASH = "a" * 64


def _seed_batch(connection: Connection) -> None:
    connection.execute(
        text(
            "INSERT INTO project (id,name,created_at,updated_at) VALUES (:id,:name,:at,:at)"
        ),
        {"id": PROJECT, "name": "project", "at": STAMP},
    )
    connection.execute(
        text(
            "INSERT INTO import_batch (id,project_id,adapter_id,adapter_version,started_at,source_root) "
            "VALUES (:id,:project,'adapter','1',:at,'source')"
        ),
        {"id": BATCH, "project": PROJECT, "at": STAMP},
    )


def _seed_identity(connection: Connection, *, alias_id: str = ALIAS) -> None:
    connection.execute(
        text(
            "INSERT INTO compound (id,canonical_smiles,isomeric_smiles,formula,molecular_weight,structure_hash,"
            "chemistry_policy_id,rdkit_version,created_at) VALUES (:id,'C','C','CH4',16.04,:hash,'v1','2026.3.4',:at)"
        ),
        {"id": COMPOUND, "hash": HASH, "at": STAMP},
    )
    connection.execute(
        text(
            "INSERT INTO molecular_state (id,compound_id,state_smiles,formal_charge,stereochemistry_signature,"
            "protonation_signature,tautomer_signature,state_hash,chemistry_policy_id,rdkit_version) "
            "VALUES (:id,:compound,'C',0,'none','neutral','canonical',:hash,'v1','2026.3.4')"
        ),
        {"id": STATE, "compound": COMPOUND, "hash": "b" * 64},
    )
    connection.execute(
        text(
            "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) "
            "VALUES (:id,'pubchem','123',:batch,:at)"
        ),
        {"id": alias_id, "batch": BATCH, "at": STAMP},
    )


@pytest.fixture
def identity_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    engine = create_sqlite_engine(tmp_path / "identity.sqlite")
    upgrade_database(engine)
    with engine.begin() as connection:
        _seed_batch(connection)
    try:
        yield engine
    finally:
        engine.dispose()


def test_upgrade_from_0001_preserves_rows_and_is_repeatable(tmp_path: Path) -> None:
    engine = create_sqlite_engine(tmp_path / "upgrade.sqlite")
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option(
        "script_location", str(Path("src/fidelichem/storage/migrations").resolve())
    )
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_initial_storage")
        connection.commit()
        connection.execute(
            text(
                "INSERT INTO project (id,name,created_at,updated_at) VALUES (:id,'old',:at,:at)"
            ),
            {"id": PROJECT, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO import_batch (id,project_id,adapter_id,adapter_version,"
                "started_at,source_root,file_count,warnings_json) VALUES "
                "(:id,:project,'adapter','1',:at,'source',1,'[]')"
            ),
            {"id": BATCH, "project": PROJECT, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO source_artifact (id,import_batch_id,path,relative_path,"
                "sha256,file_type,size_bytes,mtime) VALUES "
                "(:id,:batch,'/tmp/input.sdf','input.sdf',:hash,'sdf',4,:at)"
            ),
            {
                "id": ARTIFACT,
                "batch": BATCH,
                "hash": "d" * 64,
                "at": STAMP,
            },
        )
        connection.execute(
            text(
                "INSERT INTO audit_event (id,timestamp,action,entity_type,entity_id,"
                "source,actor_kind) VALUES (:id,:at,'created','project',:entity,'test','system')"
            ),
            {"id": AUDIT, "at": STAMP, "entity": PROJECT},
        )
        connection.commit()
    upgrade_database(engine)
    upgrade_database(engine)
    with engine.connect() as connection:
        assert current_revision(engine) == "0002_chemistry_identity"
        assert (
            connection.scalar(
                text("SELECT name FROM project WHERE id=:id"), {"id": PROJECT}
            )
            == "old"
        )
        assert connection.scalar(text("SELECT count(*) FROM import_batch")) == 1
        assert connection.scalar(text("SELECT count(*) FROM source_artifact")) == 1
        assert connection.scalar(text("SELECT count(*) FROM audit_event")) == 1
    engine.dispose()


def test_downgrade_removes_identity_tables_and_read_only_reopen_is_safe(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(tmp_path / "downgrade.sqlite")
    upgrade_database(engine)
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option(
        "script_location", str(Path("src/fidelichem/storage/migrations").resolve())
    )
    with engine.connect() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0001_initial_storage")
        connection.commit()
    assert current_revision(engine) == "0001_initial_storage"
    assert not {
        "compound",
        "molecular_state",
        "alias",
        "identity_resolution",
    }.intersection(inspect(engine).get_table_names())
    upgrade_database(engine)
    engine.dispose()
    readonly = create_sqlite_engine(tmp_path / "downgrade.sqlite", read_only=True)
    assert current_revision(readonly) == "0002_chemistry_identity"
    readonly.dispose()


def test_identity_schema_has_expected_fields_indexes_and_triggers(
    identity_engine: Engine,
) -> None:
    inspector = inspect(identity_engine)
    assert {"compound", "molecular_state", "alias", "identity_resolution"}.issubset(
        inspector.get_table_names()
    )
    assert {
        index["name"] for index in inspector.get_indexes("identity_resolution")
    } >= {
        "ix_identity_resolution_alias_id",
        "ix_identity_resolution_compound_id",
        "ix_identity_resolution_molecular_state_id",
    }
    with identity_engine.connect() as connection:
        triggers = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='trigger'")
            )
        }
        assert "trg_identity_resolution_validate_insert" in triggers
        assert connection.scalar(text("PRAGMA integrity_check")) == "ok"
        assert list(connection.execute(text("PRAGMA foreign_key_check"))) == []


def test_valid_identity_chain_and_state_ownership(identity_engine: Engine) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        connection.execute(
            text(
                "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,decided_at,actor_kind) "
                "VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
            ),
            {"id": ROOT, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,molecular_state_id,"
                "supersedes_id,decided_at,actor_kind) VALUES (:id,:alias,'reassigned',:compound,:state,:root,:at,'system')"
            ),
            {
                "id": NEXT,
                "alias": ALIAS,
                "compound": COMPOUND,
                "state": STATE,
                "root": ROOT,
                "at": STAMP,
            },
        )


def test_resolution_transitions_retract_restore_and_retract_again(
    identity_engine: Engine,
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,decided_at,actor_kind) "
                "VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
            ),
            {"id": ROOT, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,supersedes_id,decided_at,actor_kind,actor_id) "
                "VALUES (:id,:alias,'retracted',:previous,:at,'user','operator')"
            ),
            {"id": RETRACT, "alias": ALIAS, "previous": ROOT, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,supersedes_id,decided_at,"
                "actor_kind,actor_id,rationale) VALUES (:id,:alias,'restored',"
                ":compound,:previous,:at,'user','operator','reviewed')"
            ),
            {
                "id": RESTORE,
                "alias": ALIAS,
                "compound": COMPOUND,
                "previous": RETRACT,
                "at": STAMP,
            },
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,supersedes_id,decided_at,actor_kind,actor_id) "
                "VALUES (:id,:alias,'retracted',:previous,:at,'user','operator')"
            ),
            {"id": RETRACT_AGAIN, "alias": ALIAS, "previous": RESTORE, "at": STAMP},
        )


def test_insert_or_replace_cannot_delete_any_identity_row(
    identity_engine: Engine,
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,decided_at,actor_kind) "
                "VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
            ),
            {"id": ROOT, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
        )
        statements = (
            "INSERT OR REPLACE INTO compound (id,canonical_smiles,isomeric_smiles,formula,molecular_weight,structure_hash,chemistry_policy_id,rdkit_version,created_at) VALUES (:id,'C','C','CH4',1,:hash,'v1','r',:at)",
            "INSERT OR REPLACE INTO molecular_state (id,compound_id,state_smiles,formal_charge,stereochemistry_signature,protonation_signature,tautomer_signature,state_hash,chemistry_policy_id,rdkit_version) VALUES (:id,:compound,'C',0,'none','neutral','canonical',:hash,'v1','r')",
            "INSERT OR REPLACE INTO alias (id,source_system,source_value,import_batch_id,created_at) VALUES (:id,'pubchem','123',:batch,:at)",
            "INSERT OR REPLACE INTO identity_resolution (id,alias_id,decision,compound_id,decided_at,actor_kind) VALUES (:id,:alias,'confirmed',:compound,:at,'system')",
        )
        for statement in statements:
            with pytest.raises((IntegrityError, OperationalError)):
                connection.execute(
                    text(statement),
                    {
                        "id": COMPOUND
                        if "compound (" in statement
                        else (
                            STATE
                            if "molecular_state" in statement
                            else (ALIAS if "alias (" in statement else ROOT)
                        ),
                        "compound": COMPOUND,
                        "hash": HASH,
                        "batch": BATCH,
                        "alias": ALIAS,
                        "at": STAMP,
                    },
                )


def test_sql_accepts_second_alias_root_but_rejects_cross_alias_predecessor(
    identity_engine: Engine,
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        connection.execute(
            text(
                "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) "
                "VALUES (:id,'other','1',:batch,:at)"
            ),
            {"id": ALIAS_2, "batch": BATCH, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,decided_at,actor_kind) "
                "VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
            ),
            {"id": ROOT, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,decided_at,actor_kind) "
                "VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
            ),
            {"id": NEXT, "alias": ALIAS_2, "compound": COMPOUND, "at": STAMP},
        )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution "
                    "(id,alias_id,decision,compound_id,supersedes_id,decided_at,actor_kind) "
                    "VALUES (:id,:alias,'reassigned',:compound,:previous,:at,'system')"
                ),
                {
                    "id": RACE_A,
                    "alias": ALIAS_2,
                    "compound": COMPOUND,
                    "previous": ROOT,
                    "at": STAMP,
                },
            )


def test_identity_hashes_orphans_self_loop_and_state_ownership_are_rejected(
    identity_engine: Engine,
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO compound (id,canonical_smiles,isomeric_smiles,formula,"
                    "molecular_weight,structure_hash,chemistry_policy_id,rdkit_version,created_at) "
                    "VALUES (:id,'C','C','CH4',1,:hash,'v1','r',:at)"
                ),
                {"id": COMPOUND_2, "hash": HASH, "at": STAMP},
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO molecular_state (id,compound_id,state_smiles,formal_charge,"
                    "stereochemistry_signature,protonation_signature,tautomer_signature,state_hash,"
                    "chemistry_policy_id,rdkit_version) VALUES (:id,:compound,'C',0,'none',"
                    "'neutral','canonical',:hash,'v1','r')"
                ),
                {"id": NEXT, "compound": COMPOUND, "hash": "b" * 64},
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO molecular_state (id,compound_id,state_smiles,formal_charge,"
                    "stereochemistry_signature,protonation_signature,tautomer_signature,state_hash,"
                    "chemistry_policy_id,rdkit_version) VALUES (:id,:compound,'C',0,'none',"
                    "'neutral','canonical',:hash,'v1','r')"
                ),
                {
                    "id": NEXT,
                    "compound": "99999999-9999-4999-8999-999999999999",
                    "hash": "c" * 64,
                },
            )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) "
                    "VALUES (:id,'orphan','1',:batch,:at)"
                ),
                {
                    "id": ALIAS_2,
                    "batch": "99999999-9999-4999-8999-999999999999",
                    "at": STAMP,
                },
            )
        connection.execute(
            text(
                "INSERT INTO compound (id,canonical_smiles,isomeric_smiles,formula,molecular_weight,"
                "structure_hash,chemistry_policy_id,rdkit_version,created_at) VALUES (:id,'C','C','CH4',"
                "1,:hash,'v1','r',:at)"
            ),
            {"id": COMPOUND_2, "hash": "c" * 64, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO molecular_state (id,compound_id,state_smiles,formal_charge,"
                "stereochemistry_signature,protonation_signature,tautomer_signature,state_hash,"
                "chemistry_policy_id,rdkit_version) VALUES (:id,:compound,'C',0,'none','neutral',"
                "'canonical',:hash,'v1','r')"
            ),
            {"id": NEXT, "compound": COMPOUND_2, "hash": "d" * 64},
        )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,"
                    "molecular_state_id,decided_at,actor_kind) VALUES (:id,:alias,'confirmed',"
                    ":compound,:state,:at,'system')"
                ),
                {
                    "id": ROOT,
                    "alias": ALIAS,
                    "compound": COMPOUND,
                    "state": NEXT,
                    "at": STAMP,
                },
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,"
                    "supersedes_id,decided_at,actor_kind) VALUES (:id,:alias,'reassigned',"
                    ":compound,:previous,:at,'system')"
                ),
                {
                    "id": ROOT,
                    "alias": ALIAS,
                    "compound": COMPOUND,
                    "previous": ROOT,
                    "at": STAMP,
                },
            )


def _run_two_writers(
    engine_a: Engine,
    engine_b: Engine,
    sql: str,
    params_a: dict[str, str],
    params_b: dict[str, str],
) -> list[bool]:
    barrier = Barrier(2)
    results: list[bool] = []

    def worker(engine: Engine, params: dict[str, str]) -> None:
        try:
            with engine.begin() as connection:
                barrier.wait()
                connection.execute(text(sql), params)
            results.append(True)
        except (IntegrityError, OperationalError):
            results.append(False)

    first = Thread(target=worker, args=(engine_a, params_a))
    second = Thread(target=worker, args=(engine_b, params_b))
    first.start()
    second.start()
    first.join(timeout=10)
    second.join(timeout=10)
    assert not first.is_alive() and not second.is_alive()
    return results


def test_sqlite_writers_allow_one_alias_root_and_successor_winner(
    tmp_path: Path,
) -> None:
    path = tmp_path / "race.sqlite"
    setup = create_sqlite_engine(path)
    upgrade_database(setup)
    with setup.begin() as connection:
        _seed_batch(connection)
        _seed_identity(connection)
    setup.dispose()
    engine_a = create_sqlite_engine(path)
    engine_b = create_sqlite_engine(path)
    try:
        alias_results = _run_two_writers(
            engine_a,
            engine_b,
            "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) VALUES (:id,'race','1',:batch,:at)",
            {"id": RACE_A, "batch": BATCH, "at": STAMP},
            {"id": RACE_B, "batch": BATCH, "at": STAMP},
        )
        assert sorted(alias_results) == [False, True]
        with engine_a.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM alias WHERE source_system='race'")
                )
                == 1
            )
        root_results = _run_two_writers(
            engine_a,
            engine_b,
            "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,decided_at,actor_kind) VALUES (:id,:alias,'confirmed',:compound,:at,'system')",
            {"id": RACE_A, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
            {"id": RACE_B, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
        )
        assert sorted(root_results) == [False, True]
        with engine_a.connect() as connection:
            root_id = connection.scalar(
                text(
                    "SELECT id FROM identity_resolution "
                    "WHERE alias_id=:alias AND supersedes_id IS NULL"
                ),
                {"alias": ALIAS},
            )
            assert root_id in {RACE_A, RACE_B}
        successor_results = _run_two_writers(
            engine_a,
            engine_b,
            "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,supersedes_id,decided_at,actor_kind) VALUES (:id,:alias,'reassigned',:compound,:previous,:at,'system')",
            {
                "id": NEXT,
                "alias": ALIAS,
                "compound": COMPOUND,
                "previous": root_id,
                "at": STAMP,
            },
            {
                "id": RESTORE,
                "alias": ALIAS,
                "compound": COMPOUND,
                "previous": root_id,
                "at": STAMP,
            },
        )
        assert sorted(successor_results) == [False, True]
        with engine_a.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM identity_resolution WHERE supersedes_id=:root"
                    ),
                    {"root": root_id},
                )
                == 1
            )
    finally:
        engine_a.dispose()
        engine_b.dispose()


@pytest.mark.parametrize(
    "sql, params",
    [
        (
            "INSERT INTO compound (id,canonical_smiles,isomeric_smiles,formula,molecular_weight,structure_hash,chemistry_policy_id,rdkit_version,created_at) VALUES (:id,'C','C','CH4',1,:hash,'','r',:at)",
            {"id": COMPOUND_2, "hash": HASH, "at": STAMP},
        ),
        (
            "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) VALUES (:id,'PUBCHEM','1',:batch,:at)",
            {"id": ALIAS, "batch": BATCH, "at": STAMP},
        ),
        (
            "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) VALUES (:id,'pubchem','   ',:batch,:at)",
            {"id": ALIAS, "batch": BATCH, "at": STAMP},
        ),
    ],
)
def test_sql_rejects_invalid_identity_values(
    identity_engine: Engine, sql: str, params: dict[str, str]
) -> None:
    with (
        identity_engine.begin() as connection,
        pytest.raises((IntegrityError, OperationalError)),
    ):
        connection.execute(text(sql), params)


def test_sql_rejects_empty_or_malformed_inchi_keys(identity_engine: Engine) -> None:
    with identity_engine.begin() as connection:
        for value in ("", "A" * 27, "a" * 14 + "-" + "A" * 10 + "-A"):
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        "INSERT INTO compound (id,canonical_smiles,isomeric_smiles,formula,"
                        "molecular_weight,structure_hash,chemistry_policy_id,rdkit_version,"
                        "inchikey,created_at) VALUES (:id,'C','C','CH4',1,:hash,'v1','r',"
                        ":inchi,:at)"
                    ),
                    {
                        "id": COMPOUND_2,
                        "hash": value.encode().hex().ljust(64, "0")[:64],
                        "inchi": value,
                        "at": STAMP,
                    },
                )


@pytest.mark.parametrize(
    "bad_value",
    ["\t", "\n\r", "\u0085", "\u00a0", "\u2003", "\u3000", "\t\u00a0\u2003"],
)
def test_alias_source_value_uses_python_strip_whitespace(
    identity_engine: Engine, bad_value: str
) -> None:
    with identity_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) "
                "VALUES (:id,'pubchem',:value,:batch,:at)"
            ),
            {"id": COMPOUND_2, "value": bad_value, "batch": BATCH, "at": STAMP},
        )


@pytest.mark.parametrize(
    "actor_kind, actor_id",
    [
        ("system", "operator"),
        ("user", None),
        ("user", ""),
        ("user", "\u00a0"),
        ("user", "x" * 129),
        ("user", "ok\x00bad"),
    ],
)
def test_actor_sql_shape_is_non_nullable_bounded_and_nul_safe(
    identity_engine: Engine, actor_kind: str, actor_id: str | None
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution "
                    "(id,alias_id,decision,compound_id,decided_at,actor_kind,actor_id) "
                    "VALUES (:id,:alias,'confirmed',:compound,:at,:kind,:actor)"
                ),
                {
                    "id": ROOT,
                    "alias": ALIAS,
                    "compound": COMPOUND,
                    "at": STAMP,
                    "kind": actor_kind,
                    "actor": actor_id,
                },
            )


@pytest.mark.parametrize("rationale", ["\t", "\u00a0", "x\x00y", "x" * 1025])
def test_restored_rationale_sql_is_bounded_and_nonblank(
    identity_engine: Engine, rationale: str
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,compound_id,decided_at,actor_kind) "
                "VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
            ),
            {"id": ROOT, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
        )
        connection.execute(
            text(
                "INSERT INTO identity_resolution "
                "(id,alias_id,decision,supersedes_id,decided_at,actor_kind,actor_id) "
                "VALUES (:id,:alias,'retracted',:previous,:at,'user','operator')"
            ),
            {"id": RETRACT, "alias": ALIAS, "previous": ROOT, "at": STAMP},
        )
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution "
                    "(id,alias_id,decision,compound_id,supersedes_id,decided_at,"
                    "actor_kind,actor_id,rationale) VALUES (:id,:alias,'restored',"
                    ":compound,:previous,:at,'user','operator',:rationale)"
                ),
                {
                    "id": RESTORE,
                    "alias": ALIAS,
                    "compound": COMPOUND,
                    "previous": RETRACT,
                    "at": STAMP,
                    "rationale": rationale,
                },
            )


def test_molecular_weight_rejects_infinite_sql_value(identity_engine: Engine) -> None:
    with identity_engine.begin() as connection, pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO compound (id,canonical_smiles,isomeric_smiles,formula,"
                "molecular_weight,structure_hash,chemistry_policy_id,rdkit_version,created_at) "
                "VALUES (:id,'C','C','CH4',:weight,:hash,'v1','r',:at)"
            ),
            {
                "id": COMPOUND_2,
                "weight": float("inf"),
                "hash": "c" * 64,
                "at": STAMP,
            },
        )


def test_alias_natural_key_and_resolution_graph_constraints(
    identity_engine: Engine,
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO alias (id,source_system,source_value,import_batch_id,created_at) VALUES (:id,'pubchem','123',:batch,:at)"
                ),
                {"id": COMPOUND_2, "batch": BATCH, "at": STAMP},
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,supersedes_id,decided_at,actor_kind) VALUES (:id,:alias,'reassigned',:compound,'missing',:at,'system')"
                ),
                {"id": ROOT, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
            )
        connection.execute(
            text(
                "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,decided_at,actor_kind) VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
            ),
            {"id": ROOT, "alias": ALIAS, "compound": COMPOUND, "at": STAMP},
        )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,decided_at,actor_kind) VALUES (:id,:alias,'confirmed',:compound,:at,'system')"
                ),
                {"id": NEXT, "alias": ALIAS, "compound": COMPOUND_2, "at": STAMP},
            )


def test_identity_tables_are_append_only_and_fk_restrictive(
    identity_engine: Engine,
) -> None:
    with identity_engine.begin() as connection:
        _seed_identity(connection)
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(text("DELETE FROM alias WHERE id=:id"), {"id": ALIAS})
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text("UPDATE compound SET formula='x' WHERE id=:id"), {"id": COMPOUND}
            )
        with pytest.raises((IntegrityError, OperationalError)):
            connection.execute(
                text(
                    "INSERT INTO identity_resolution (id,alias_id,decision,compound_id,supersedes_id,decided_at,actor_kind) VALUES (:id,:alias,'reassigned',:compound,:missing,:at,'system')"
                ),
                {
                    "id": ROOT,
                    "alias": ALIAS,
                    "compound": COMPOUND,
                    "missing": "99999999-9999-4999-8999-999999999999",
                    "at": STAMP,
                },
            )
