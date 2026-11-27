"""Python ast extractor: FreeCAD's .py files -> one JSONL file of fact records.

uv run cg-extract-py --out ~/.cache/codegraph/runs/<run>
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

from codegraph_schema import SCHEMA_VERSION, JsonlWriter


def _files(freecad: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(freecad), "ls-files", "src/*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [f for f in out if not f.startswith("src/3rdParty/")]


def _module_name(rel: str) -> str:
    return rel.removeprefix("src/").removesuffix(".py").replace("/", ".")


def _extract(w: JsonlWriter, rel: str, tree: ast.Module) -> None:
    mod = _module_name(rel)
    w.write(
        {
            "t": "pymod",
            "id": mod,
            "file": rel,
            "lines": max((getattr(n, "end_lineno", 0) or 0 for n in tree.body), default=0),
            "doc": (ast.get_docstring(tree) or "")[:200],
        }
    )

    def visit(node, parent_id: str, in_class: bool) -> None:
        for n in ast.iter_child_nodes(node):
            if isinstance(n, ast.ClassDef):
                cid = f"{parent_id}.{n.name}"
                w.write(
                    {
                        "t": "pyclass",
                        "id": cid,
                        "name": n.name,
                        "parent": parent_id,
                        "file": rel,
                        "line": n.lineno,
                        "end": n.end_lineno,
                        "bases": [ast.unparse(b) for b in n.bases],
                    }
                )
                visit(n, cid, True)
            elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fid = f"{parent_id}.{n.name}"
                cc = 1 + sum(
                    isinstance(
                        x,
                        (
                            ast.If,
                            ast.For,
                            ast.While,
                            ast.Try,
                            ast.With,
                            ast.BoolOp,
                            ast.IfExp,
                            ast.ExceptHandler,
                            ast.comprehension,
                        ),
                    )
                    for x in ast.walk(n)
                )
                w.write(
                    {
                        "t": "pyfunc",
                        "id": fid,
                        "name": n.name,
                        "parent": parent_id,
                        "method": in_class,
                        "file": rel,
                        "line": n.lineno,
                        "end": n.end_lineno,
                        "args": len(n.args.args),
                        "cc": cc,
                        "decorators": [ast.unparse(d) for d in n.decorator_list],
                    }
                )
                visit(n, fid, False)
            elif isinstance(n, ast.Import):
                for a in n.names:
                    w.write(
                        {"t": "edge", "k": "imports", "src": mod, "dst": a.name, "line": n.lineno}
                    )
            elif isinstance(n, ast.ImportFrom):
                base = ("." * n.level) + (n.module or "")
                w.write(
                    {
                        "t": "edge",
                        "k": "imports",
                        "src": mod,
                        "dst": base,
                        "names": [a.name for a in n.names][:50],
                        "line": n.lineno,
                    }
                )
            else:
                visit(n, parent_id, in_class)

    visit(tree, mod, False)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--freecad", default=str(Path.home() / "src/FreeCAD"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    freecad, out = Path(a.freecad), Path(a.out).expanduser()
    files = _files(freecad)
    bad = 0
    with JsonlWriter(out / "python.jsonl") as w:
        w.write({"t": "run", "tool": "extract-py", "schema": SCHEMA_VERSION, "files": len(files)})
        for rel in files:
            try:
                tree = ast.parse((freecad / rel).read_bytes(), filename=rel)
            except (SyntaxError, ValueError) as exc:
                bad += 1
                w.write({"t": "pyerror", "file": rel, "error": str(exc)[:200]})
                continue
            _extract(w, rel, tree)
    print(f"python: {len(files)} files, {bad} unparsable, {w.count} records -> {w.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
