"""Dependency boundaries; transaction atomicity is tested separately."""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                parts = path.relative_to(APP.parent).with_suffix("").parts[:-1]
                module = ".".join(parts[: len(parts) - node.level + 1]) + (
                    "." + module if module else ""
                )
            yield module
            yield from (module + "." + a.name for a in node.names)


def test_services_do_not_import_http_schemas_or_orm_models():
    failures = []
    for path in (APP / "domains").rglob("*service.py"):
        for name in imports(path):
            parts = name.split(".")
            if (
                name.startswith("fastapi")
                or "schemas" in parts
                or (name.startswith("app.domains.") and "models" in parts)
                or name.startswith("sqlalchemy.ext.asyncio")
            ):
                failures.append(f"{path.relative_to(APP)}: {name}")
    assert not failures, "\n".join(failures)


def test_domain_services_do_not_import_other_domains_services_or_use_cases():
    failures = []
    for path in (APP / "domains").rglob("*service.py"):
        domain = path.relative_to(APP / "domains").parts[0]
        for name in imports(path):
            parts = name.split(".")
            if name.startswith("app.use_cases") or (
                name.startswith("app.domains.")
                and parts[2] != domain
                and any(p.endswith("service") for p in parts[3:])
            ):
                failures.append(f"{path.relative_to(APP)}: {name}")
    assert not failures, "\n".join(failures)


def test_entities_and_contracts_do_not_depend_on_transport_or_persistence():
    failures = []
    for path in (APP / "domains").rglob("*.py"):
        if path.name not in {"entities.py", "contracts.py"}:
            continue
        for name in imports(path):
            parts = name.split(".")
            if name.startswith(("fastapi", "starlette", "sqlalchemy")) or any(
                p in {"models", "repository", "dependencies", "router", "schemas"}
                for p in parts
            ):
                failures.append(f"{path.relative_to(APP)}: {name}")
    assert not failures, "\n".join(failures)


def test_repositories_never_commit():
    failures = []
    for path in (APP / "domains").rglob("*.py"):
        tree = ast.parse(path.read_text())
        # Also covers repositories colocated with export-job entities/services.
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not node.name.endswith(
                "Repository"
            ):
                continue
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "commit"
                ):
                    failures.append(f"{path.relative_to(APP)}:{child.lineno}")
    assert not failures, "\n".join(failures)
