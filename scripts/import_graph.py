#!/usr/bin/env python3
"""Emit ripcale's `app.*` import graph as a Markdown migration baseline.

Scans every ``import app...`` / ``from app... import ...`` statement under
``app/`` and ``tests/`` and prints (to stdout):

- summary counts,
- "hub" modules (imported by the most files),
- a mutual-import (2-cycle) check,
- the full importer -> target edge list.

Usage::

    # freeze a baseline
    python scripts/import_graph.py --test-count 542 > docs/MIGRATION_BASELINE.md

    # later (F76): regenerate and diff against the frozen baseline
    python scripts/import_graph.py | diff docs/MIGRATION_BASELINE.md -

Submodule imports are resolved against the filesystem, so
``from app.services import actions`` records ``app.services.actions`` (the
submodule) rather than the ``app.services`` package.
"""
from __future__ import annotations

import argparse
import ast
import datetime
from collections import Counter, defaultdict
from pathlib import Path


def module_name(path: Path, root: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _is_submodule(root: Path, module: str, name: str) -> bool:
    base = root.joinpath(*module.split("."), name)
    return base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()


def collect(root: Path) -> tuple[dict[str, set[str]], Counter]:
    edges: dict[str, set[str]] = defaultdict(set)

    def add(importer: str, target: str) -> None:
        edges[importer].add(target)

    for base in ("app", "tests"):
        for path in sorted((root / base).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            importer = module_name(path, root)
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "app":
                        for a in node.names:
                            add(importer, f"app.{a.name}")
                    elif module.startswith("app"):
                        for a in node.names:
                            add(importer, f"{module}.{a.name}" if _is_submodule(root, module, a.name) else module)
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name.startswith("app"):
                            add(importer, a.name)

    # one count per (importer, target) edge, not per imported name
    counts: Counter = Counter(target for targets in edges.values() for target in targets)
    return edges, counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--test-count", type=int, default=None)
    args = ap.parse_args()
    root = Path(args.root)
    edges, counts = collect(root)

    print("# ripcale — Migration Baseline (import graph)\n")
    print(
        f"> Frozen snapshot generated {datetime.date.today().isoformat()} by "
        "`scripts/import_graph.py`. Regenerate and diff against this in F76 to "
        "confirm no stale imports remain.\n"
    )
    if args.test_count is not None:
        print(f"- **Test count at baseline:** {args.test_count}")
    print(f"- **Importer files with `app.*` imports:** {len(edges)}")
    print(f"- **Distinct targets:** {len(counts)}\n")

    print("## Hub modules (imported by N files)\n")
    print("| imports | module |")
    print("|---:|---|")
    for target, count in counts.most_common():
        print(f"| {count} | `{target}` |")

    print("\n## Mutual imports (2-cycle check)\n")
    app_mods = {m for m in edges if m.startswith("app")}
    pairs, seen = [], set()
    for a in app_mods:
        for b in edges.get(a, ()):
            if b in edges and a in edges[b] and a != b:
                key = tuple(sorted((a, b)))
                if key not in seen:
                    seen.add(key)
                    pairs.append(key)
    if pairs:
        for a, b in sorted(pairs):
            print(f"- `{a}` <-> `{b}`")
    else:
        print("None (no direct mutual imports).")

    print("\n## Full edge list (importer → target)\n")
    print("```")
    for importer in sorted(edges):
        for target in sorted(edges[importer]):
            print(f"{importer} -> {target}")
    print("```")


if __name__ == "__main__":
    main()
