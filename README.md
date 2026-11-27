# codegraph

Turns the [FreeCAD](https://github.com/FreeCAD/FreeCAD) source tree into a queryable graph in Neo4j.

- **Extractors** (uv workspace under `packages/`) write regenerable JSON Lines fact records:
  - `cg-extract-cpp`: C++ via libclang 21, using the FreeCAD build's `compile_commands.json` and its
    own toolchain — symbols (stable USRs), calls, inheritance, type use, includes, per-function
    lines and complexity. Parallel and resumable.
  - `cg-extract-py`: Python modules, classes, functions, imports.
  - `cg-extract-git`: per-file churn and authors, co-change pairs.
- **Loader** (next): records into Neo4j. **Annotations**: files in `annotations/`, keyed by
  symbol ID, overlaid on the facts.
- The graph UI is a separate project: [qt-graphkit](https://github.com/resmond/qt-graphkit).

Design: [docs/decisions.md](docs/decisions.md). Status: [docs/status.md](docs/status.md).

```
uv sync
uv run cg-extract-cpp --out ~/.cache/codegraph/runs/test --limit 20   # quick test
scripts/overnight-parse.sh                                             # full run (~2-3 h)
```

License: LGPL-2.1-or-later. See [LICENSE](LICENSE).
