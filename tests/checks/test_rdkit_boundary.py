import ast
from pathlib import Path


def test_rdkit_imports_are_confined_to_chemistry_package() -> None:
    source_root = Path(__file__).parents[2] / "src" / "fidelichem"
    chemistry_root = source_root / "chemistry"
    violations: list[str] = []
    for path in source_root.rglob("*.py"):
        if chemistry_root in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            if any(
                module == "rdkit" or module.startswith("rdkit.") for module in modules
            ):
                violations.append(str(path))
    assert violations == []
