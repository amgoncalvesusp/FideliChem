import importlib
import tomllib
from importlib.metadata import entry_points
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def read_toml(relative_path: str) -> dict[str, object]:
    with (ROOT / relative_path).open("rb") as stream:
        return tomllib.load(stream)


@pytest.mark.config
def test_runtime_dependencies_include_phase_one_storage_stack() -> None:
    pyproject = read_toml("pyproject.toml")
    project = pyproject["project"]

    assert isinstance(project, dict)
    assert project["requires-python"] == ">=3.12,<3.13"
    assert project["dependencies"] == [
        "PySide6>=6.8,<7",
        "pydantic>=2.10,<3",
        "SQLAlchemy>=2.0,<3",
        "alembic>=1.13,<2",
        "rdkit==2026.3.4",
    ]
    dependency_groups = pyproject["dependency-groups"]
    assert isinstance(dependency_groups, dict)
    assert "hypothesis>=6.0" in dependency_groups["dev"]


@pytest.mark.config
def test_codex_configuration_enables_bounded_multi_agent_work() -> None:
    config = read_toml(".codex/config.toml")
    agents = config["agents"]

    assert config["features"] == {"multi_agent": True}
    assert isinstance(agents, dict)
    assert agents["max_threads"] == 6
    assert agents["max_depth"] == 1
    assert {
        "luna_explorer",
        "luna_worker",
        "luna_adapter",
        "luna_tests",
        "luna_docs",
        "terra_reviewer",
        "sol_architect",
    }.issubset(agents)


@pytest.mark.config
def test_ci_covers_phase_zero_gate_on_both_operating_systems() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    for required_text in (
        "ubuntu-latest",
        "windows-latest",
        'python-version: "3.12"',
        "uv lock --check",
        "uv run ruff check .",
        "uv run mypy src/fidelichem",
        "--cov-fail-under=80",
        "uv run pip-audit",
        "uv build",
    ):
        assert required_text in workflow


@pytest.mark.config
def test_installed_gui_entry_point_resolves_to_application_main() -> None:
    installed_entry_points = {
        entry_point.name: entry_point.value
        for entry_point in entry_points(group="gui_scripts")
    }

    assert installed_entry_points["fidelichem-gui"] == (
        "fidelichem.gui.application:main"
    )
    module = importlib.import_module("fidelichem.gui.application")
    assert callable(module.main)


@pytest.mark.config
def test_ci_pins_official_actions_to_immutable_shas() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    expected_actions = {
        "actions/checkout": ("11d5960a326750d5838078e36cf38b85af677262", "v4"),
        "actions/setup-python": (
            "a26af69be951a213d495a4c3e4e4022e16d87065",
            "v5",
        ),
        "astral-sh/setup-uv": (
            "d0d8abe699bfb85fec6de9f7adb5ae17292296ff",
            "v6",
        ),
    }

    for action, (sha, tag) in expected_actions.items():
        assert f"uses: {action}@{sha} # {tag}" in workflow
        assert f"uses: {action}@{tag}" not in workflow
