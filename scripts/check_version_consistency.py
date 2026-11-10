#!/usr/bin/env python3
"""Enforce workspace-internal dependency version floors across ``packages/python/*``.

Per-package version lockstep across ``pyproject.toml``, ``__init__.py``,
``server.json``, ``Cargo.toml``, ``Cargo.lock``, ``package.json``, TypeScript
source literals, ``dbt_project.yml``, ``goldenmatch_pg.control``, and
``docs/.docs-sweep.json`` -- as well as manifest-registration coverage via
``registered-manifests`` -- lives declaratively in ``blockwatch.toml``.

This script is the single owner of the sibling-package dependency floor check
(allowing self-referential extras such as ``all = ["goldenmatch[...]"]`` while
requiring a version floor on every sibling workspace package). It needs PEP 508
parsing and the live workspace roster, so it is deliberately NOT mirrored in
``blockwatch.toml``.

Run: ``python scripts/check_version_consistency.py``
"""
from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_REQ_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
# A requirement is floored if it carries ANY version or URL constraint. "!="
# alone is deliberately NOT enough: it excludes a bad release without
# establishing a minimum, so the resolver may still pick something older than
# the symbols the code imports.
_FLOOR_RE = re.compile(r"(>=|==|~=|>|@|===)")


def _workspace_dist_names() -> dict[str, Path]:
    """Distribution name -> its pyproject, for every in-repo Python package."""
    out: dict[str, Path] = {}
    for pyproject in sorted((ROOT / "packages" / "python").glob("*/pyproject.toml")):
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        name = data.get("project", {}).get("name")
        if name:
            out[name.lower().replace("_", "-")] = pyproject
    return out


def _check_internal_floors(errors: list[str]) -> int:
    """Every dependency on a SIBLING workspace package must carry a floor."""
    local = _workspace_dist_names()
    checked = 0
    for name, pyproject in sorted(local.items()):
        project = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {})
        groups: list[tuple[str, list]] = [("dependencies", project.get("dependencies") or [])]
        for extra, reqs in (project.get("optional-dependencies") or {}).items():
            groups.append(("optional-dependencies." + extra, reqs))
        for group, reqs in groups:
            for req in reqs:
                m = _REQ_NAME_RE.match(req.strip())
                if not m:
                    continue
                dep = m.group(1).lower().replace("_", "-")
                if dep not in local or dep == name:
                    continue
                if not _FLOOR_RE.search(req):
                    errors.append(
                        f"{pyproject.relative_to(ROOT)} [{group}]: {req!r} depends "
                        f"on workspace package {dep!r} with no version floor"
                    )
        checked += 1
    return checked


def main() -> int:
    errors: list[str] = []
    checked = _check_internal_floors(errors)

    if errors:
        print(f"Internal dependency floor check FAILED ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"Internal dependency floors OK: {checked} workspace packages checked."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
